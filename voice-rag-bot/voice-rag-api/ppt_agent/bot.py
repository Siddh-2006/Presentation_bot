import asyncio
import base64
import os
import shutil
import tempfile
import numpy as np
import re
from loguru import logger
from playwright.async_api import async_playwright, Page, Browser, Playwright

from .session import PresentationSession, State

# Use system Chrome if Playwright-managed Chromium is not downloaded.
# Override via env: PPT_CHROME_PATH=/path/to/chrome
CHROME_EXECUTABLE: str | None = os.getenv(
    "PPT_CHROME_PATH",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
) or None
from .vad_engine import VADEngine
from .presenter import Presenter


class MeetBot:
    BROWSER_ARGS = [
        "--use-fake-ui-for-media-stream",
        "--auto-select-desktop-capture-source=Entire screen",
        "--enable-usermedia-screen-capturing",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--disable-background-networking",
        "--autoplay-policy=no-user-gesture-required",
    ]

    # JS injected to intercept the microphone before Jitsi loads
    _PRELOAD_GUM_JS = """
    // Create global context immediately
    window._pptAudioCtx = window._pptAudioCtx || new AudioContext({ sampleRate: 24000 });
    window._pptDest     = window._pptDest || window._pptAudioCtx.createMediaStreamDestination();

    // Create TrustedTypes policy in main page context so its callback stays alive forever
    if (window.trustedTypes && window.trustedTypes.createPolicy) {
        if (!window._pptGlobalPolicy) {
            try {
                window._pptGlobalPolicy = window.trustedTypes.createPolicy('ppt-global-policy', {
                    createHTML: (string) => string
                });
            } catch (e) {
                console.warn('[Bot] Failed to create global TrustedTypes policy', e);
            }
        }
    }

    // Unlock AudioContext on any user click (e.g. when Playwright clicks "Join now")
    document.addEventListener('click', () => {
        if (window._pptAudioCtx && window._pptAudioCtx.state === 'suspended') {
            window._pptAudioCtx.resume().catch(e => console.warn('[Bot] AudioContext resume failed:', e));
        }
    }, { capture: true, once: true });

    // Hook enumerateDevices to ensure we report at least one audio input and one video input
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
        const origEnumerate = navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices);
        navigator.mediaDevices.enumerateDevices = async function() {
            let devices = [];
            try {
                devices = await origEnumerate();
            } catch (e) {
                console.warn("[Bot GUM] Original enumerateDevices failed:", e);
            }
            
            const hasAudioInput = devices.some(d => d.kind === 'audioinput');
            const hasVideoInput = devices.some(d => d.kind === 'videoinput');
            
            if (!hasAudioInput) {
                devices.push({
                    deviceId: 'mock-audio-device-id',
                    kind: 'audioinput',
                    label: 'Virtual Microphone (Presentation Bot)',
                    groupId: 'mock-group-id',
                    toJSON: function() { return this; }
                });
            }
            if (!hasVideoInput) {
                devices.push({
                    deviceId: 'mock-video-device-id',
                    kind: 'videoinput',
                    label: 'Virtual Camera (Presentation Bot)',
                    groupId: 'mock-group-id',
                    toJSON: function() { return this; }
                });
            }
            return devices;
        };
    }

    // Override getUserMedia to substitute our audio stream and/or mock camera track
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        const origGUM = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
        navigator.mediaDevices.getUserMedia = async function(constraints) {
            console.log("[Bot GUM] getUserMedia called with constraints:", JSON.stringify(constraints));
            
            const tracks = [];
            
            if (constraints && constraints.audio) {
                const audioTrack = window._pptDest.stream.getAudioTracks()[0];
                if (audioTrack) {
                    tracks.push(audioTrack);
                    console.log("[Bot GUM] Substituted virtual microphone track");
                } else {
                    console.warn("[Bot GUM] No virtual microphone track found in window._pptDest");
                }
            }
            
            if (constraints && constraints.video) {
                try {
                    const canvas = document.createElement('canvas');
                    canvas.width = 640;
                    canvas.height = 480;
                    const ctx = canvas.getContext('2d');
                    ctx.fillStyle = 'black';
                    ctx.fillRect(0, 0, canvas.width, canvas.height);
                    ctx.fillStyle = '#4285F4';
                    ctx.font = '20px Arial';
                    ctx.fillText('Presentation Bot Camera', 50, 240);
                    
                    const canvasStream = canvas.captureStream(10);
                    const videoTrack = canvasStream.getVideoTracks()[0];
                    if (videoTrack) {
                        tracks.push(videoTrack);
                        console.log("[Bot GUM] Substituted mock camera track from canvas");
                    }
                } catch (e) {
                    console.error("[Bot GUM] Failed to create mock video track:", e);
                }
            }
            
            if (tracks.length > 0) {
                return new MediaStream(tracks);
            }
            
            return origGUM(constraints);
        };
    }
    """

    # JS injected into the page to set up virtual mic audio injection
    _INJECT_AUDIO_JS = """
    window._pptAudioCtx = window._pptAudioCtx || new AudioContext({ sampleRate: 24000 });
    window._pptDest     = window._pptDest || window._pptAudioCtx.createMediaStreamDestination();
    window._pptNextTime = window._pptNextTime || 0;
    window._pptNodes    = window._pptNodes || [];

    async function pptPlayChunk(base64Data) {
        if (!base64Data) return;
        const raw      = atob(base64Data);
        // Ensure length is a multiple of 4 to prevent Float32Array RangeError
        const validLen = raw.length - (raw.length % 4);
        if (validLen === 0) return;
        const bytes    = new Uint8Array(validLen);
        for (let i = 0; i < validLen; i++) bytes[i] = raw.charCodeAt(i);
        const floats   = new Float32Array(bytes.buffer);
        if (floats.length === 0) return;
        const buf      = window._pptAudioCtx.createBuffer(1, floats.length, 24000);
        buf.copyToChannel(floats, 0);
        
        if (window._pptAudioCtx.state === 'suspended') {
            try {
                await Promise.race([
                    window._pptAudioCtx.resume(),
                    new Promise(r => setTimeout(r, 500))
                ]);
            } catch (e) {
                console.warn("[Bot] AudioContext resume error:", e);
            }
        }
        
        const src      = window._pptAudioCtx.createBufferSource();
        src.buffer     = buf;
        src.connect(window._pptAudioCtx.destination);
        src.connect(window._pptDest);
        
        const now = window._pptAudioCtx.currentTime;
        // Add a 800ms buffer when starting a new audio stream to prevent initial load cracking
        if (window._pptNextTime <= now) {
            window._pptNextTime = now + 0.8;
        }
        
        window._pptNodes.push(src);
        src.onended = () => {
            window._pptNodes = window._pptNodes.filter(n => n !== src);
        };
        
        src.start(window._pptNextTime);
        window._pptNextTime += buf.duration;
    }
    window.pptPlayChunk = pptPlayChunk;
    """

    # JS to capture incoming remote audio and forward as PCM via console
    _CAPTURE_AUDIO_JS = """
    (function() {
        if (window._pptHookInstalled) return;
        window._pptHookInstalled = true;
        console.log("PPT_HOOK: install start");

        const TARGET_RATE = 16000;
        let ctx = null;
        let initPromise = null;
        let workletLoaded = false;
        let actualRate = TARGET_RATE;
        window._pptHookedTracks = window._pptHookedTracks || new Set();

        const workletCode = `
            class AudioCaptureProcessor extends AudioWorkletProcessor {
                constructor() {
                    super();
                    this.rawBuffer = [];
                    this.downsampledBuffer = [];
                    this.nextRawIndex = 0.0;
                    this.frameCount = 0;
                }

                process(inputs, outputs, parameters) {
                    const input = inputs[0];
                    this.frameCount++;

                    if (!input || input.length === 0) return true;
                    const ch0 = input[0];
                    if (!ch0 || ch0.length === 0) return true;
                    const ch1 = input[1];

                    // (Removed diagnostic check)

                    // Average both channels if stereo
                    const channel = new Float32Array(ch0.length);
                    for (let i = 0; i < ch0.length; i++) {
                        channel[i] = ch1 ? (ch0[i] + ch1[i]) / 2 : ch0[i];
                    }

                    // Append input raw samples
                    for (let i = 0; i < channel.length; i++) {
                        this.rawBuffer.push(channel[i]);
                    }

                    const ratio = sampleRate / 16000;
                    while (this.nextRawIndex + 1 < this.rawBuffer.length) {
                        const baseIdx = Math.floor(this.nextRawIndex);
                        const alpha = this.nextRawIndex - baseIdx;
                        const sample = this.rawBuffer[baseIdx] * (1 - alpha) + this.rawBuffer[baseIdx + 1] * alpha;
                        this.downsampledBuffer.push(sample);
                        this.nextRawIndex += ratio;
                    }

                    // Slice the consumed raw samples
                    const cutIdx = Math.floor(this.nextRawIndex);
                    if (cutIdx > 0) {
                        this.rawBuffer = this.rawBuffer.slice(cutIdx);
                        this.nextRawIndex -= cutIdx;
                    }

                    // Send 4096-sample Int16 packages
                    while (this.downsampledBuffer.length >= 4096) {
                        const frame = this.downsampledBuffer.slice(0, 4096);
                        this.downsampledBuffer = this.downsampledBuffer.slice(4096);

                        const int16 = new Int16Array(4096);
                        let maxInt16 = 0;
                        for (let i = 0; i < 4096; i++) {
                            const s = Math.max(-1, Math.min(1, frame[i]));
                            int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                            maxInt16 = Math.max(maxInt16, Math.abs(int16[i]));
                        }

                        // Send completely silent frames as a lightweight string to avoid CDP flooding
                        if (maxInt16 === 0) {
                            console.log("SILENCE:" + track.id + ":4096");
                            continue;
                        }

                        this.port.postMessage(int16);
                    }

                    return true;
                }
            }
            registerProcessor('audio-capture-processor', AudioCaptureProcessor);
        `;

        function ensureContext() {
            if (initPromise) return initPromise;
            initPromise = (async () => {
                ctx = new AudioContext(); // let Chrome pick its native rate
                actualRate = ctx.sampleRate;
                console.log("PPT_DEBUG: native rate=" + actualRate);
                
                // Add click listener to unlock AudioContext when Playwright clicks Join
                document.addEventListener('click', () => {
                    if (ctx && ctx.state === 'suspended') {
                        ctx.resume().catch(e => console.warn('AudioContext resume failed:', e));
                        console.log("PPT_HOOK: Capture AudioContext resumed on click!");
                    }
                }, { capture: true, once: true });

                try {
                    await ctx.resume();
                    console.log("PPT_HOOK: AudioContext resumed, state=" + ctx.state);
                } catch (err) {
                    console.log("PPT_HOOK: AudioContext resume FAILED (waiting for click): " + err);
                }

                try {
                    const blob = new Blob([workletCode], { type: 'application/javascript' });
                    const url = URL.createObjectURL(blob);
                    await ctx.audioWorklet.addModule(url);
                    workletLoaded = true;
                    console.log("PPT_HOOK: AudioWorklet module loaded successfully");
                } catch (err) {
                    console.log("PPT_HOOK: AudioWorklet addModule FAILED: " + err);
                }
                return ctx;
            })();
            return initPromise;
        }

        async function hookStream(stream, source_label) {
            if (!stream) return;
            const audioTracks = stream.getAudioTracks();
            if (audioTracks.length === 0) return;

            // Check if we have already captured all tracks in this stream
            let hasNewTrack = false;
            for (const track of audioTracks) {
                if (!window._pptHookedTracks.has(track.id)) {
                    window._pptHookedTracks.add(track.id);
                    hasNewTrack = true;
                }
            }
            if (!hasNewTrack) return;

            const track = audioTracks[0];
            
            console.log("PPT_HOOK: hooking stream from " + source_label);

            const audioCtx = await ensureContext();
            if (!workletLoaded) {
                console.log("PPT_HOOK: Cannot hook stream, worklet not loaded");
                // Allow retry by deleting tracks from set
                for (const track of audioTracks) {
                    window._pptHookedTracks.delete(track.id);
                }
                return;
            }

            try {
                const source = audioCtx.createMediaStreamSource(stream);
                const processor = new AudioWorkletNode(audioCtx, 'audio-capture-processor');
                source.connect(processor);
                processor.connect(audioCtx.destination);
                
                processor.port.onmessage = (e) => {
                    if (e.data && e.data.debug) {
                        console.log("PPT_WORKLET_DEBUG: " + JSON.stringify(e.data));
                        return;
                    }
                    const int16 = e.data; // Int16Array of size 4096
                    const u8 = new Uint8Array(int16.buffer);
                    let binary = '';
                    for (let i = 0; i < u8.length; i++) {
                        binary += String.fromCharCode(u8[i]);
                    }
                    console.log("PPT_HOOK: voice detected on " + track.id);
                    console.log("PCM:" + track.id + ":" + btoa(binary));
                };
                console.log("PPT_HOOK: successfully connected AudioWorkletNode");
            } catch (err) {
                console.log("PPT_HOOK: error setting up AudioWorkletNode: " + err);
                for (const track of audioTracks) {
                    window._pptHookedTracks.delete(track.id);
                }
            }
        }

        // Hook 1: HTMLMediaElement.prototype.srcObject setter
        const desc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'srcObject');
        if (desc && desc.set) {
            const origSet = desc.set;
            Object.defineProperty(HTMLMediaElement.prototype, 'srcObject', {
                set: function(stream) {
                    if (stream && stream instanceof MediaStream) {
                        hookStream(stream, "HTMLMediaElement.srcObject");
                    }
                    return origSet.call(this, stream);
                },
                get: desc.get,
                configurable: true,
                enumerable: true
            });
            console.log("PPT_HOOK: srcObject setter hooked");
        }

        // Hook 2: HTMLMediaElement.play
        const origPlay = HTMLMediaElement.prototype.play;
        HTMLMediaElement.prototype.play = function() {
            const stream = this.srcObject;
            if (stream && stream instanceof MediaStream) {
                hookStream(stream, "HTMLMediaElement.play");
            }
            return origPlay.apply(this, arguments);
        };

        // Hook 3: RTCPeerConnection.prototype.setRemoteDescription
        if (typeof RTCPeerConnection !== 'undefined') {
            const origSetRemoteDescription = RTCPeerConnection.prototype.setRemoteDescription;
            RTCPeerConnection.prototype.setRemoteDescription = function() {
                this.addEventListener('track', (e) => {
                    if (e.streams && e.streams.length > 0) {
                        hookStream(e.streams[0], "RTCPeerConnection.track");
                    } else if (e.track && e.track.kind === 'audio') {
                        const stream = new MediaStream([e.track]);
                        hookStream(stream, "RTCPeerConnection.track_fallback");
                    }
                });
                return origSetRemoteDescription.apply(this, arguments);
            };
            console.log("PPT_HOOK: RTCPeerConnection hooked");
        }

        // Hook 4: MutationObserver for dynamically added <audio> elements
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                mutation.addedNodes.forEach((node) => {
                    if (node.tagName && node.tagName.toLowerCase() === 'audio') {
                        console.log("PPT_HOOK: found new <audio> element in DOM");
                        if (node.srcObject) hookStream(node.srcObject, "MutationObserver");
                        node.addEventListener('play', () => {
                            if (node.srcObject) hookStream(node.srcObject, "AudioEvent_play");
                        });
                        // Poll for srcObject in case it's set later without triggering setter
                        const poller = setInterval(() => {
                            if (node.srcObject) {
                                hookStream(node.srcObject, "AudioPoller");
                            }
                        }, 1000);
                        setTimeout(() => clearInterval(poller), 15000); // Stop polling after 15s
                    }
                });
            });
        });
        
        // Wait for DOM to be ready before observing
        if (document.body || document.documentElement) {
            observer.observe(document.body || document.documentElement, { childList: true, subtree: true });
        } else {
            window.addEventListener('DOMContentLoaded', () => {
                observer.observe(document.body || document.documentElement, { childList: true, subtree: true });
            });
        }

        console.log("PPT_HOOK: install complete");
    })();
    """

    def __init__(self, session: PresentationSession, presenter: Presenter):
        self.session   = session
        self.presenter = presenter
        self.vad_engine: VADEngine | None = None
        self._browser:    Browser | None    = None
        self._page:       Page | None       = None
        self._playwright: Playwright | None = None
        self._capture_task: asyncio.Task | None = None
        self._tmp_profile: str | None = None   # ephemeral Chrome profile dir
        
        # Dedicated VAD worker queue and thread setup
        import queue
        import threading
        self._vad_queue = queue.Queue()
        self._vad_thread = None
        self._vad_stop_event = threading.Event()
        self._pcm_count = 0

    def set_vad_engine(self, vad_engine: VADEngine):
        self.vad_engine = vad_engine

    # ── Meeting join ──────────────────────────────────────────────────────────

    async def start(self, meeting_url: str) -> bool:
        """
        Launch Chromium headless, navigate to meeting URL, attempt to join.
        Returns True if joined successfully (best-effort), False on hard error.
        """
        try:
            self._playwright = await async_playwright().start()
            # Use a persistent profile so Google logins are saved across sessions
            self._tmp_profile = os.path.join(os.getcwd(), "bot_chrome_profile")
            os.makedirs(self._tmp_profile, exist_ok=True)
            logger.info(f"[Bot] Using persistent Chrome profile: {self._tmp_profile}")
            launch_kwargs: dict = {
                "headless": True,
                "args": self.BROWSER_ARGS,
                "user_data_dir": self._tmp_profile,
            }
            if CHROME_EXECUTABLE and os.path.exists(CHROME_EXECUTABLE):
                launch_kwargs["executable_path"] = CHROME_EXECUTABLE
                logger.info(f"[Bot] Using system Chrome: {CHROME_EXECUTABLE}")
            self._browser = await self._playwright.chromium.launch_persistent_context(
                self._tmp_profile,
                headless=True,
                args=self.BROWSER_ARGS,
                executable_path=CHROME_EXECUTABLE if CHROME_EXECUTABLE and os.path.exists(CHROME_EXECUTABLE) else None,
                permissions=["camera", "microphone", "clipboard-read", "clipboard-write"],
                bypass_csp=True,
            )
            # launch_persistent_context returns context directly
            context = self._browser
            await context.add_init_script(self._PRELOAD_GUM_JS)
            await context.add_init_script(self._CAPTURE_AUDIO_JS)
            await context.add_init_script(self._INJECT_AUDIO_JS)
            
            pages = context.pages
            if len(pages) > 0:
                self._page = pages[0]
            else:
                self._page = await context.new_page()
                
            self._page.on("console", self._on_console_message)
            self._page.on("pageerror", lambda exc: logger.error(f"[BROWSER ERROR] {exc}"))

            url_lower = meeting_url.lower()
            
            # Auto-prepend https:// if missing to prevent Playwright invalid URL error
            if not url_lower.startswith("http://") and not url_lower.startswith("https://"):
                meeting_url = f"https://{meeting_url}"
                url_lower = meeting_url.lower()

            # Rewrite Zoom URLs to use the Web Client
            if "zoom.us" in url_lower and "/j/" in url_lower:
                meeting_url = meeting_url.replace("/j/", "/wc/join/")
                logger.info(f"[Bot] Rewrote Zoom URL to Web Client: {meeting_url}")

            logger.info(f"[Bot] Navigating to {meeting_url}")
            await self._page.goto(meeting_url, timeout=30_000)

            joined = False
            if "meet.google.com" in url_lower:
                joined = await self._join_google_meet()
            elif "zoom.us" in url_lower:
                joined = await self._join_zoom()
            elif "jit.si" in url_lower or "jitsi" in url_lower:
                joined = await self._join_jitsi()
            else:
                logger.info("[Bot] Unknown meeting platform — navigated best-effort")
                joined = True

            if joined:
                asyncio.create_task(self._debug_dumper_loop())
            return joined

        except Exception as e:
            logger.error(f"[Bot] start() failed: {e}")
            return False

    async def _debug_dumper_loop(self):
        logger.info("[Bot] Debug dumper loop started")
        js_dump = """
        (() => {
            let res = [];
            res.push("Hook installed: " + (window._pptHookInstalled || "NOT SET"));
            if (window._pptAudioCtx) {
                res.push("AudioContext state: " + window._pptAudioCtx.state);
                res.push("AudioContext sampleRate: " + window._pptAudioCtx.sampleRate);
                res.push("AudioContext workletLoaded: " + (typeof window._pptHookedTracks !== 'undefined'));
            } else {
                res.push("No global _pptAudioCtx found");
            }
            
            const mediaEls = document.querySelectorAll('audio, video');
            res.push("Found " + mediaEls.length + " media elements");
            mediaEls.forEach((el, i) => {
                const stream = el.srcObject;
                res.push("  [" + i + "] tag=" + el.tagName + " paused=" + el.paused + " muted=" + el.muted + " srcObject=" + !!stream);
                if (stream instanceof MediaStream) {
                    res.push("      audioTracks=" + stream.getAudioTracks().length);
                    stream.getAudioTracks().forEach(t => {
                        const isCaptured = window._pptHookedTracks ? window._pptHookedTracks.has(t.id) : false;
                        res.push("      track id=" + t.id + " enabled=" + t.enabled + " muted=" + t.muted + " readyState=" + t.readyState + " captured=" + isCaptured);
                    });
                }
            });
            return res.join("\\n");
        })()
        """
        while self._page and not self._page.is_closed():
            try:
                await asyncio.sleep(5.0)
                if self._page:
                    dump_str = await self._page.evaluate(js_dump)
                    logger.debug(f"=== PPT DEBUG DUMP ===\nPCM Chunks Received: {self._pcm_count}\n{dump_str}\n======================")
            except Exception as e:
                logger.debug(f"[Bot] Debug dumper error: {e}")

    async def _join_google_meet(self) -> bool:
        """Google Meet join flow."""
        try:
            page = self._page

            # Wait for the page to stabilize
            await page.wait_for_load_state("networkidle", timeout=10000)
            await page.wait_for_timeout(2000)

            # Find name input (varies by Meet version)
            name_selectors = [
                'input[aria-label*="name" i]',
                'input[placeholder*="name" i]',
                'input[data-initial-value]',
                'input[type="text"]' # Broad fallback
            ]
            
            # Wait for at least one name input to appear before interacting
            for sel in name_selectors:
                try:
                    await page.wait_for_selector(sel, state="visible", timeout=5000)
                    await page.fill(sel, "Presentation Bot", timeout=3000)
                    logger.info(f"[Bot] Filled name field: {sel}")
                    break
                except Exception:
                    continue

            # Ensure camera is turned off before joining
            try:
                cam_btn = page.locator('div[aria-label*="Turn off camera" i], button[aria-label*="Turn off camera" i]').first
                if await cam_btn.is_visible(timeout=3000):
                    await cam_btn.click(timeout=1000)
                    logger.info("[Bot] Turned off G-Meet camera (pre-join)")
            except Exception:
                pass

            # Click join button
            join_selectors = [
                'text="Ask to join"',
                'text="Join now"',
                'text="Join"',
                '[role="button"]:has-text("Ask to join")',
                '[role="button"]:has-text("Join now")',
            ]
            joined = False
            for sel in join_selectors:
                try:
                    await page.click(sel, timeout=3000)
                    logger.info(f"[Bot] Clicked G-Meet join button: {sel}")
                    joined = True
                    break
                except Exception:
                    continue
            
            if not joined:
                # Super fallback: look for any button containing "join" (case insensitive)
                try:
                    await page.click('button:has-text("join" i)', timeout=3000)
                    joined = True
                except Exception:
                    pass
            
            if not joined:
                # Check if we bypassed the lobby and are already in the meeting
                try:
                    if await page.locator('button[aria-label*="Leave call" i], button[aria-label*="leave call" i]').is_visible(timeout=2000):
                        joined = True
                        logger.info("[Bot] Detected we are already in the meeting (bypassed lobby).")
                except Exception:
                    pass

            if not joined:
                await page.screenshot(path="failed_join_gmeet.png")
                logger.warning("[Bot] Could not find G-Meet join button. Screenshot saved to failed_join_gmeet.png")
                return False

            # Wait for the pre-join screen to disappear (which means we were admitted)
            # The name input is a good indicator of the pre-join screen
            logger.info("[Bot] Waiting in G-Meet lobby (Ask to Join) until admitted...")
            try:
                for sel in name_selectors:
                    # Wait for the element to be hidden or detached
                    await page.wait_for_selector(sel, state="hidden", timeout=120_000)
            except Exception:
                pass # timeout or detached

            # Wait for meeting to stabilize
            await page.wait_for_timeout(5000)
            logger.info("[Bot] Successfully joined Google Meet (Admitted from lobby!)")
            
            # Start screen sharing
            await self._start_screen_share()

            return True

        except Exception as e:
            logger.warning(f"[Bot] Google Meet join error: {e}")
            return True   # best-effort


    async def _join_zoom(self) -> bool:
        """Zoom Web Client join flow."""
        try:
            page = self._page
            await page.wait_for_load_state("networkidle", timeout=10000)
            await page.wait_for_timeout(3000)

            # Sometimes Zoom asks for cookies consent
            try:
                await page.click('button:has-text("Agree")', timeout=2000)
            except Exception:
                pass

            # Find name input
            name_selectors = [
                'input[name="inputname"]',
                'input[placeholder*="Your Name" i]',
                'input[type="text"]'
            ]
            
            for sel in name_selectors:
                try:
                    await page.wait_for_selector(sel, state="visible", timeout=5000)
                    await page.fill(sel, "Presentation Bot", timeout=4000)
                    logger.info(f"[Bot] Filled Zoom name: {sel}")
                    break
                except Exception:
                    continue

            # Ensure camera is turned off
            try:
                cam_btn = page.locator('button[aria-label*="Stop Video" i], button[title*="Stop Video" i]').first
                if await cam_btn.is_visible(timeout=2000):
                    await cam_btn.click(timeout=1000)
                    logger.info("[Bot] Turned off Zoom camera (pre-join)")
            except Exception:
                pass
                
            # Click join button
            join_selectors = [
                'button:has-text("Join")',
                '.join-btn'
            ]
            joined = False
            for sel in join_selectors:
                try:
                    await page.click(sel, timeout=3000)
                    logger.info(f"[Bot] Clicked Zoom join: {sel}")
                    joined = True
                    break
                except Exception:
                    continue
                    
            if not joined:
                await page.screenshot(path="failed_join_zoom.png")
                logger.warning("[Bot] Could not find Zoom join button. Screenshot saved to failed_join_zoom.png")
                return False

            # Wait in lobby until admitted
            logger.info("[Bot] Waiting in Zoom lobby until admitted...")
            try:
                await page.wait_for_selector('text="Please wait"', state="hidden", timeout=120_000)
                # Ensure main toolbar is visible meaning we fully joined
                await page.wait_for_selector('.footer__inner', state="visible", timeout=30000)
                logger.info("[Bot] Admitted to Zoom room!")
                
                # Start screen sharing
                await self._start_screen_share()
                return True
            except Exception as e:
                logger.warning(f"[Bot] Timed out waiting in Zoom lobby: {e}")
                return False

        except Exception as e:
            logger.warning(f"[Bot] Zoom join error: {e}")
            return True   # best-effort

    async def _join_jitsi(self) -> bool:
        """Jitsi / meet.jit.si join flow."""
        try:
            page = self._page
            await page.wait_for_timeout(3000)

            # Fill display name
            name_selectors = [
                '#premeeting-name-input',
                'input[placeholder*="name" i]',
                'input[aria-label*="name" i]',
            ]
            for sel in name_selectors:
                try:
                    await page.fill(sel, "Presentation Bot", timeout=4000)
                    logger.info(f"[Bot] Filled Jitsi name: {sel}")
                    break
                except Exception:
                    continue

            # Click join / start meeting button
            join_selectors = [
                'div[data-testid="prejoin.joinMeeting"]',
                'button:has-text("Join meeting")',
                'button:has-text("Start meeting")',
                'button:has-text("Join")',
            ]
            for sel in join_selectors:
                try:
                    await page.click(sel, timeout=5000)
                    logger.info(f"[Bot] Clicked Jitsi join: {sel}")
                    
                    # Start screen sharing
                    await self._start_screen_share()
                    return True
                except Exception:
                    continue

            await page.wait_for_timeout(5000)
            logger.info("[Bot] Joined Jitsi room")
            return True

        except Exception as e:
            logger.error(f"[Bot] Failed to join Jitsi: {e}")
            return False

    async def _start_screen_share(self):
        """Attempts to click the Present/Share Screen button for the current meeting platform."""
        if not self._page:
            return
        
        page = self._page
        logger.info("[Bot] Attempting to start screen sharing...")
        await page.wait_for_timeout(3000)
        
        # Selectors for various platforms' share screen buttons
        # Note: Google Meet often uses div[role="button"] instead of button
        share_selectors = [
            '[aria-label*="Present now" i]',
            '[data-tooltip*="Present now" i]',
            '[aria-label*="Share screen" i]',
            '[aria-label*="Present screen" i]',
            '[aria-label*="Share Screen" i]',
            '[title*="Share Screen" i]',
            '[aria-label*="Toggle screenshare" i]',
            '[aria-label*="Share your screen" i]',
            'button:has-text("Present now")',
            'button:has(i:text("present_to_all"))',
            'div[role="button"]:has(i:text("present_to_all"))'
        ]
        
        clicked_share = False
        for sel in share_selectors:
            try:
                # Use evaluate to click cleanly without scrolling issues
                found = await page.evaluate(f'''() => {{
                    let el = document.querySelector(`{sel}`);
                    if (el) {{
                        el.click();
                        return true;
                    }}
                    return false;
                }}''')
                
                # If pure JS click fails, try Playwright native click
                if not found:
                    loc = page.locator(sel).first
                    if await loc.is_visible(timeout=1000):
                        await loc.click(timeout=1000)
                        found = True
                        
                if found:
                    logger.info(f"[Bot] Clicked Share Screen button via selector: {sel}")
                    clicked_share = True
                    break
            except Exception as e:
                logger.debug(f"Selector {sel} failed: {e}")
                continue
                
        # If CSS selectors didn't match, try Playwright's accessible name search
        if not clicked_share:
            role_names = ["Present now", "Share screen", "Present screen", "Share Screen", "Toggle screenshare", "Share your screen"]
            for name in role_names:
                try:
                    loc = page.get_by_role("button", name=re.compile(name, re.IGNORECASE)).first
                    if await loc.is_visible(timeout=1000):
                        await loc.click(timeout=1000)
                        logger.info(f"[Bot] Clicked Share Screen button via role/name: {name}")
                        clicked_share = True
                        break
                except Exception:
                    continue

        # If still not clicked, search for text in all elements
        if not clicked_share:
            text_queries = ["Present now", "Share Screen", "Share screen", "Present screen"]
            for q in text_queries:
                try:
                    found = await page.evaluate(f'''(text) => {{
                        let elements = Array.from(document.querySelectorAll('*'));
                        for (let el of elements) {{
                            const content = (el.innerText || el.textContent || "").trim();
                            if (content.toLowerCase() === text.toLowerCase()) {{
                                el.click();
                                return true;
                            }}
                        }}
                        return false;
                    }}''', q)
                    if found:
                        logger.info(f"[Bot] Clicked Share Screen button via matching text content: {q}")
                        clicked_share = True
                        break
                except Exception:
                    continue

        if clicked_share:
            # Google Meet requires a second click to choose "Entire Screen"
            await page.wait_for_timeout(1000)
            meet_entire_screen = [
                '[aria-label*="Entire screen" i]',
                'li[aria-label*="Entire screen" i]',
                'text="Entire screen"',
                'text="Your entire screen"'
            ]
            for sel in meet_entire_screen:
                try:
                    if sel.startswith('text='):
                        text = sel.replace('text=', '').replace('"', '')
                        found = await page.evaluate(f'''(text) => {{
                            let elements = Array.from(document.querySelectorAll('*'));
                            for (let el of elements) {{
                                const content = (el.innerText || el.textContent || "").trim();
                                if (content.toLowerCase().includes(text.toLowerCase())) {{
                                    el.click();
                                    return true;
                                }}
                            }}
                            return false;
                        }}''', text)
                        if found:
                            logger.info(f"[Bot] Clicked 'Entire screen' option via text match: {text}")
                            break
                    else:
                        loc = page.locator(sel).first
                        if await loc.is_visible(timeout=1000):
                            await loc.click()
                            logger.info(f"[Bot] Clicked 'Entire screen' option in G-Meet via selector: {sel}")
                            break
                except Exception:
                    pass
            logger.info("[Bot] Screen sharing initiated")
        else:
            logger.warning("[Bot] Could not find a Share Screen button")

    # ── Audio capture ─────────────────────────────────────────────────────────

    def _vad_worker(self):
        import base64
        import numpy as np
        import queue
        
        logger.info("[VAD Worker] Dedicated thread started")
        remainders = {}
        while not self._vad_stop_event.is_set():
            try:
                # Wait up to 100ms for a frame
                item = self._vad_queue.get(timeout=0.1)
            except queue.Empty:
                continue
                
            try:
                stream_id, b64_data = item
                raw = base64.b64decode(b64_data)
                if stream_id not in remainders:
                    remainders[stream_id] = bytearray()
                remainders[stream_id].extend(raw)

                # Feed exactly 1024-byte (512 int16 samples) chunks to VAD
                while len(remainders[stream_id]) >= 1024:
                    chunk = remainders[stream_id][:1024]
                    if self.vad_engine:
                        self.vad_engine.process_frame(stream_id, bytes(chunk))
                    remainders[stream_id] = remainders[stream_id][1024:]
            except Exception as e:
                logger.warning(f"[VAD Worker] Frame processing error: {e}")
            finally:
                self._vad_queue.task_done()
        logger.info("[VAD Worker] Dedicated thread stopped")

    def _on_console_message(self, msg):
        text = msg.text
        if text.startswith("PCM:"):
            self._pcm_count += 1
            if self._pcm_count % 50 == 0:
                logger.debug(f"[DEBUG] PCM chunks received so far: {self._pcm_count}")
            parts = text.split(":", 2)
            if len(parts) == 3:
                stream_id = parts[1]
                b64_data = parts[2]
                if self.vad_engine and self._vad_thread and self._vad_thread.is_alive():
                    self._vad_queue.put_nowait((stream_id, b64_data))
        elif text.startswith("SILENCE:"):
            parts = text.split(":", 2)
            if len(parts) == 3:
                import base64
                stream_id = parts[1]
                num_samples = int(parts[2])
                silent_bytes = b'\x00' * (num_samples * 2)
                b64_data = base64.b64encode(silent_bytes).decode("ascii")
                if self.vad_engine and self._vad_thread and self._vad_thread.is_alive():
                    self._vad_queue.put_nowait((stream_id, b64_data))
        elif text.startswith("PPT_WORKLET_DEBUG:"):
            logger.info(f"[Bot JS] {text}")
        elif text.startswith("PPT_HOOK:"):
            logger.info(f"[Bot JS] {text}")
        else:
            logger.debug(f"[BROWSER {msg.type}] {text}")

    async def start_audio_capture(self, vad_engine: VADEngine):
        """
        Registers the VAD engine and wires presenter audio output → inject_audio_chunk().
        Capture script runs early via add_init_script.
        """
        self.set_vad_engine(vad_engine)

        # Wire presenter TTS output → inject into meeting virtual mic safely from background thread
        main_loop = asyncio.get_running_loop()
        self.presenter.set_audio_output(
            lambda chunk: asyncio.run_coroutine_threadsafe(
                self.inject_audio_chunk(chunk), main_loop
            )
        )
        
        # Start VAD background worker thread
        import threading
        self._vad_stop_event.clear()
        self._vad_thread = threading.Thread(target=self._vad_worker, daemon=True)
        self._vad_thread.start()
        
        logger.info("[Bot] Audio capture initialized (preloaded listeners active and VAD worker running)")

    # ── Audio injection ────────────────────────────────────────────────────────

    async def stop_audio_playback(self):
        """Instantly flush all queued TTS audio in the browser."""
        if not self._page: return
        js = """
        if (window._pptNodes) {
            window._pptNodes.forEach(n => {
                try { n.stop(); n.disconnect(); } catch(e) {}
            });
            window._pptNodes = [];
        }
        if (window._pptAudioCtx) {
            window._pptNextTime = window._pptAudioCtx.currentTime;
        }
        """
        try:
            await self._page.evaluate(js)
            logger.info("[Bot] Flushed audio playback queue")
        except Exception as e:
            logger.warning(f"[Bot] stop_audio_playback error: {e}")

    async def inject_audio_chunk(self, audio_np: np.ndarray):
        """
        Play a TTS audio chunk (float32 @ 24kHz) through the virtual mic
        by calling window.pptPlayChunk() in the page JS context.
        """
        if self._page is None or len(audio_np) == 0:
            return
        try:
            # Ensure float32 and contiguous memory
            arr   = np.ascontiguousarray(audio_np, dtype=np.float32)
            raw   = arr.tobytes()
            b64   = base64.b64encode(raw).decode("ascii")
            await self.play_audio_chunk(b64)
        except Exception as e:
            logger.warning(f"[Bot] inject_audio_chunk error: {e}")

    async def play_audio_chunk(self, base64_pcm: str):
        """Sends a base64-encoded float32 PCM chunk to the browser's Web Audio API context."""
        if not self._page:
            return
        import asyncio
        try:
            await asyncio.wait_for(
                self._page.evaluate("base64Data => window.pptPlayChunk(base64Data)", base64_pcm),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.error("[Bot] play_audio_chunk timed out waiting for page.evaluate")
        except Exception as e:
            logger.error(f"[Bot] Failed to inject audio chunk: {e}")

    async def wait_for_audio_idle(self, max_wait_secs: float = 30.0):
        """Wait until the browser's Web Audio playback queue is empty."""
        if not self._page:
            return
        import asyncio
        import time
        try:
            start = time.time()
            while time.time() - start < max_wait_secs:
                result = await asyncio.wait_for(
                    self._page.evaluate("""() => {
                        const exists = typeof window._pptNodes !== 'undefined';
                        const count = exists ? window._pptNodes.length : -1;
                        return { exists: exists, count: count, playing: !!(exists && count > 0) };
                    }"""),
                    timeout=3.0
                )
                
                if not result["exists"]:
                    logger.debug("[Bot] window._pptNodes does not exist yet on this page")
                
                is_playing = result["playing"]
                if not is_playing:
                    break
                await asyncio.sleep(0.05)
        except asyncio.TimeoutError:
            logger.warning("[Bot] wait_for_audio_idle timed out waiting for page.evaluate")
        except Exception as e:
            logger.warning(f"[Bot] wait_for_audio_idle error: {e}")

    async def stop_audio(self):
        pass

    # ── Slide display ─────────────────────────────────────────────────────────

    async def show_slide(self, slide_html: str):
        """
        Inject slide HTML as a full-screen overlay on the current page.
        For MVP: overlays the slide content so screen share captures it.
        """
        if self._page is None:
            return
        import asyncio
        escaped = slide_html.replace("`", "\\`").replace("${", "\\${")
        try:
            await asyncio.wait_for(
                self._page.evaluate(f"""
                    (() => {{
                        let overlay = document.getElementById('ppt-slide-overlay');
                        if (!overlay) {{
                            overlay = document.createElement('div');
                            overlay.id = 'ppt-slide-overlay';
                            overlay.style.cssText = `
                                position: fixed; top: 0; left: 0;
                                width: 100vw; height: 100vh;
                                z-index: 999999;
                                background: white;
                                display: flex; align-items: center; justify-content: center;
                            `;
                            document.body.appendChild(overlay);
                        }}
                        
                        let safeHtml = `{escaped}`;
                        if (window._pptGlobalPolicy) {{
                            try {{
                                safeHtml = window._pptGlobalPolicy.createHTML(safeHtml);
                            }} catch (e) {{
                                console.error('Global policy createHTML failed:', e);
                            }}
                        }}
                        overlay.innerHTML = safeHtml;
                    }})();
                """),
                timeout=5.0
            )
            logger.info("[Bot] Slide injected into page overlay")
        except asyncio.TimeoutError:
            logger.error("[Bot] show_slide timed out waiting for page.evaluate")
        except Exception as e:
            logger.error(f"[Bot] show_slide failed: {e}")

    # ── Teardown ──────────────────────────────────────────────────────────────

    async def leave(self):
        """Close browser and stop all background tasks."""
        # Stop VAD background thread
        self._vad_stop_event.set()
        if self._vad_thread:
            self._vad_thread = None
            
        # Clear VAD queue
        import queue
        self._vad_queue = queue.Queue()

        if self._capture_task:
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass

        if self._page:
            await self._page.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

        # We no longer delete the profile so cookies (like Google Login) are preserved!
        logger.info(f"[Bot] Session {self.session.session_id} left meeting")

