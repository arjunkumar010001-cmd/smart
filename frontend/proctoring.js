/**
 * ProctoringClient — Smart Assessment Proctoring (Phase 2)
 * ========================================================
 * Standalone module. Imported ONLY on assessment pages via <script> tag.
 * Never bundled into candidate.js.
 *
 * Step 2: Copy/paste, fullscreen, right-click, DevTools, warning modal
 * Step 3: BlazeFace camera monitoring (face detection every 2s)
 * Step 4: Web Audio voice baseline + anomaly detection
 */
(function () {
    'use strict';

    // ── Guard: only run if SocketIO client is loaded ────────────────────
    if (typeof io === 'undefined') {
        console.warn('[Proctoring] Socket.IO client not loaded — proctoring disabled');
        return;
    }

    // ═══════════════════════════════════════════════════════════════════
    // Constants
    // ═══════════════════════════════════════════════════════════════════
    const FULLSCREEN_GRACE_MS = 10000;          // 10 seconds to restore
    const DEVTOOLS_THRESHOLD_PX = 160;          // width/height delta
    const FACE_DETECT_INTERVAL_MS = 2000;       // check faces every 2s
    const SNAPSHOT_MAX_BYTES = 500 * 1024;      // 500KB limit per snapshot
    const SNAPSHOT_JPEG_QUALITY = 0.6;          // JPEG quality for canvas export
    const AUDIO_ANALYSIS_INTERVAL_MS = 500;     // audio check every 500ms
    const AUDIO_BASELINE_DURATION_MS = 10000;   // 10s baseline window
    const AUDIO_BASELINE_TIMEOUT_MS = 30000;    // 30s max wait for speech
    const AUDIO_SPEECH_THRESHOLD = 30;          // min dB above noise floor to count as speech
    const AUDIO_ANOMALY_SUSTAIN_COUNT = 6;      // 3s sustained anomaly (6 × 500ms)
    const EVENTS = Object.freeze({
        COPY_PASTE: 'copy_paste',
        TAB_SWITCH: 'tab_switch',
        FULLSCREEN_EXIT: 'fullscreen_exit',
        RIGHT_CLICK: 'right_click',
        DEVTOOLS_OPEN: 'devtools_open',
        FACE_NOT_DETECTED: 'face_not_detected',
        MULTIPLE_FACES: 'multiple_faces',
        AUDIO_ANOMALY: 'audio_anomaly',
        SECONDARY_VOICE: 'secondary_voice',
    });

    // ═══════════════════════════════════════════════════════════════════
    // ProctoringClient
    // ═══════════════════════════════════════════════════════════════════
    class ProctoringClient {
        /**
         * @param {Object} opts
         * @param {string} opts.sessionId - Smart assessment session ID
         * @param {string} opts.token     - JWT bearer token
         * @param {string} [opts.socketUrl] - SocketIO server URL (default: current origin)
         */
        constructor(opts = {}) {
            this.sessionId = opts.sessionId;
            this.token = opts.token;
            this.socketUrl = opts.socketUrl || window.location.origin;
            this.socket = null;

            // State
            this._destroyed = false;
            this._fullscreenGraceTimer = null;
            this._isFullscreenActive = false;
            this._warningModalVisible = false;
            this._devtoolsWasOpen = false;

            // Camera / BlazeFace state (Step 3)
            this._blazefaceModel = null;
            this._faceDetectInterval = null;
            this._videoEl = null;
            this._cameraStream = null;
            this._snapshotCanvas = null;

            // Audio monitoring state (Step 4)
            this._audioCtx = null;
            this._audioAnalyser = null;
            this._audioStream = null;
            this._audioInterval = null;
            this._audioBaseline = null;        // { peakFreqBin, peakMagnitude, avgEnergy }
            this._baselineRecording = false;
            this._baselineStartTime = 0;
            this._baselineSpeechDetected = false;
            this._baselineSamples = [];        // array of { peakBin, magnitude, energy }
            this._anomalySustainCount = 0;     // counter for sustained anomaly

            // Recording state (MediaRecorder)
            this._mediaRecorder = null;
            this._recordingChunks = [];
            this._chunkIndex = 0;
            this._recordingUploadInterval = null;
            this._flushPromise = null;             // Promise lock against double-flush

            // Bound handlers (for later removal)
            this._onCopy = this._handleCopyPaste.bind(this, 'copy');
            this._onCut = this._handleCopyPaste.bind(this, 'cut');
            this._onPaste = this._handleCopyPaste.bind(this, 'paste');
            this._onContextMenu = this._handleContextMenu.bind(this);
            this._onFullscreenChange = this._handleFullscreenChange.bind(this);
            this._onVisibilityChange = this._handleVisibilityChange.bind(this);
            this._onResize = this._handleResize.bind(this);
        }

        // ═══════════════════════════════════════════════════════════════
        // Lifecycle
        // ═══════════════════════════════════════════════════════════════

        /**
         * Start proctoring: connect socket, attach listeners, enter fullscreen.
         */
        start() {
            if (this._destroyed) return;

            // 1. Connect SocketIO
            this.socket = io(this.socketUrl, {
                auth: { token: this.token },
                transports: ['websocket', 'polling'],
                reconnection: true,
                reconnectionDelay: 2000,
                reconnectionDelayMax: 8000,
                reconnectionAttempts: 10,
            });

            this.socket.on('connect', () => {
                console.log('[Proctoring] SocketIO connected:', this.socket.id);
            });
            this.socket.on('disconnect', (reason) => {
                console.warn('[Proctoring] SocketIO disconnected:', reason);
            });

            // 2. Listen for server consequences
            this.socket.on('warning_issued', (data) => this._showWarningModal(data));
            this.socket.on('session_terminated', (data) => this._handleTermination(data));
            this.socket.on('session_resumed', () => this._onSessionResumed());
            this.socket.on('proctoring_ack', (data) => {
                console.log('[Proctoring] ACK:', data);
            });

            // 3. Attach browser event listeners
            document.addEventListener('copy', this._onCopy, true);
            document.addEventListener('cut', this._onCut, true);
            document.addEventListener('paste', this._onPaste, true);
            document.addEventListener('contextmenu', this._onContextMenu, true);
            document.addEventListener('fullscreenchange', this._onFullscreenChange);
            document.addEventListener('visibilitychange', this._onVisibilityChange);
            window.addEventListener('resize', this._onResize);

            // 4. Enter fullscreen
            this._enterFullscreen();

            // 5. Start camera + BlazeFace (Step 3)
            this._initCamera();

            // 6. Start audio monitoring (Step 4)
            this._initAudio();

            console.log('[Proctoring] Started for session:', this.sessionId);
        }

        /**
         * Tear down all listeners and disconnect socket.
         */
        destroy() {
            this._destroyed = true;
            if (this._fullscreenGraceTimer) {
                clearTimeout(this._fullscreenGraceTimer);
            }

            // Stop face detection loop
            if (this._faceDetectInterval) {
                clearInterval(this._faceDetectInterval);
                this._faceDetectInterval = null;
            }

            // Stop recording and flush final chunk (best-effort)
            if (this._recordingUploadInterval) {
                clearInterval(this._recordingUploadInterval);
                this._recordingUploadInterval = null;
            }
            if (this._mediaRecorder && this._mediaRecorder.state !== 'inactive') {
                try { this._mediaRecorder.stop(); } catch (e) { /* already stopped */ }
            }
            // Promise lock: reuse existing flush or start new one
            this._flushPromise = this._flushPromise || this._flushRecordingChunk(true);
            this._flushPromise.catch(() => { });

            // Stop camera stream
            if (this._cameraStream) {
                this._cameraStream.getTracks().forEach(t => t.stop());
                this._cameraStream = null;
            }

            // Stop audio monitoring
            if (this._audioInterval) {
                clearInterval(this._audioInterval);
                this._audioInterval = null;
            }
            if (this._audioStream) {
                this._audioStream.getTracks().forEach(t => t.stop());
                this._audioStream = null;
            }
            if (this._audioCtx) {
                this._audioCtx.close().catch(() => { });
                this._audioCtx = null;
            }

            document.removeEventListener('copy', this._onCopy, true);
            document.removeEventListener('cut', this._onCut, true);
            document.removeEventListener('paste', this._onPaste, true);
            document.removeEventListener('contextmenu', this._onContextMenu, true);
            document.removeEventListener('fullscreenchange', this._onFullscreenChange);
            document.removeEventListener('visibilitychange', this._onVisibilityChange);
            window.removeEventListener('resize', this._onResize);

            // Remove modal if visible
            const modal = document.getElementById('proctoring-warning-modal');
            if (modal) modal.remove();

            if (this.socket) {
                this.socket.disconnect();
                this.socket = null;
            }

            console.log('[Proctoring] Destroyed');
        }

        // ═══════════════════════════════════════════════════════════════
        // Event Emission
        // ═══════════════════════════════════════════════════════════════

        /**
         * Emit a proctoring event to the server.
         * @param {string} eventType - One of the EVENTS constants
         * @param {Object} [metadata] - Additional context
         */
        _emit(eventType, metadata = {}) {
            if (!this.socket || !this.socket.connected) {
                console.warn('[Proctoring] Cannot emit — socket not connected');
                return;
            }
            this.socket.emit('proctoring_event', {
                event_type: eventType,
                session_id: this.sessionId,
                timestamp: new Date().toISOString(),
                metadata: metadata,
            });
        }

        // ═══════════════════════════════════════════════════════════════
        // Copy / Paste / Cut
        // ═══════════════════════════════════════════════════════════════

        _handleCopyPaste(action, e) {
            // Allow copy/paste in the Monaco code editor (it's in an iframe)
            if (e.target && e.target.closest && e.target.closest('.monaco-editor')) {
                return; // Don't block coding questions
            }

            e.preventDefault();
            e.stopPropagation();

            this._emit(EVENTS.COPY_PASTE, { action: action });
            console.warn(`[Proctoring] ${action} blocked and reported`);
        }

        // ═══════════════════════════════════════════════════════════════
        // Right-Click Suppression
        // ═══════════════════════════════════════════════════════════════

        _handleContextMenu(e) {
            // Suppress on the assessment area
            const assessmentArea = document.getElementById('saAssessmentView');
            if (assessmentArea && assessmentArea.contains(e.target)) {
                e.preventDefault();
                this._emit(EVENTS.RIGHT_CLICK, {});
            }
        }

        // ═══════════════════════════════════════════════════════════════
        // Full-Screen Enforcement
        // ═══════════════════════════════════════════════════════════════

        _enterFullscreen() {
            const el = document.documentElement;
            const rfs = el.requestFullscreen
                || el.webkitRequestFullscreen
                || el.mozRequestFullScreen
                || el.msRequestFullscreen;
            if (rfs) {
                rfs.call(el).then(() => {
                    this._isFullscreenActive = true;
                }).catch((err) => {
                    console.warn('[Proctoring] Fullscreen request denied:', err.message);
                });
            }
        }

        _handleFullscreenChange() {
            const isFullscreen = !!(
                document.fullscreenElement
                || document.webkitFullscreenElement
                || document.mozFullScreenElement
                || document.msFullscreenElement
            );

            if (isFullscreen) {
                // Restored fullscreen — cancel grace timer
                this._isFullscreenActive = true;
                if (this._fullscreenGraceTimer) {
                    clearTimeout(this._fullscreenGraceTimer);
                    this._fullscreenGraceTimer = null;
                    console.log('[Proctoring] Fullscreen restored within grace period');
                }
                return;
            }

            // Exited fullscreen
            this._isFullscreenActive = false;
            this._emit(EVENTS.FULLSCREEN_EXIT, {});

            // Start grace period — server pauses timer via warning_issued event.
            // If candidate doesn't restore within 10s, client emits another
            // fullscreen_exit which will accumulate toward termination.
            this._fullscreenGraceTimer = setTimeout(() => {
                if (!this._isFullscreenActive && !this._destroyed) {
                    // Grace period expired without restoration
                    this._emit(EVENTS.FULLSCREEN_EXIT, {
                        reason: 'grace_period_expired',
                    });
                }
            }, FULLSCREEN_GRACE_MS);
        }

        // ═══════════════════════════════════════════════════════════════
        // Tab Switch Detection
        // ═══════════════════════════════════════════════════════════════

        _handleVisibilityChange() {
            if (document.hidden) {
                this._emit(EVENTS.TAB_SWITCH, { action: 'tab_hidden' });
            }
        }

        // ═══════════════════════════════════════════════════════════════
        // DevTools Detection (heuristic — severity 2, log only)
        // ═══════════════════════════════════════════════════════════════

        _handleResize() {
            const widthDelta = window.outerWidth - window.innerWidth;
            const heightDelta = window.outerHeight - window.innerHeight;

            const devtoolsLikelyOpen = (
                widthDelta > DEVTOOLS_THRESHOLD_PX
                || heightDelta > DEVTOOLS_THRESHOLD_PX
            );

            if (devtoolsLikelyOpen && !this._devtoolsWasOpen) {
                this._devtoolsWasOpen = true;
                this._emit(EVENTS.DEVTOOLS_OPEN, {
                    widthDelta: widthDelta,
                    heightDelta: heightDelta,
                });
                console.warn('[Proctoring] DevTools likely opened (logged, no termination)');
            } else if (!devtoolsLikelyOpen) {
                this._devtoolsWasOpen = false;
            }
        }


        // ═══════════════════════════════════════════════════════════════
        // Camera / BlazeFace (Step 3)
        // ═══════════════════════════════════════════════════════════════

        /**
         * Initialize camera stream and load BlazeFace model.
         * Gracefully degrades if getUserMedia unavailable (needs HTTPS).
         */
        async _initCamera() {
            try {
                // 1. Get video element
                this._videoEl = document.getElementById('proctor-cam');
                if (!this._videoEl) {
                    console.warn('[Proctoring] #proctor-cam element not found — camera disabled');
                    return;
                }

                // 2. Request camera access
                if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                    console.warn('[Proctoring] getUserMedia unavailable (HTTPS required) — camera disabled');
                    return;
                }
                this._cameraStream = await navigator.mediaDevices.getUserMedia({
                    video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
                    audio: false,
                });
                this._videoEl.srcObject = this._cameraStream;
                await this._videoEl.play();
                console.log('[Proctoring] Camera stream active');

                // 3. Create snapshot canvas — sized dynamically at capture time
                //    to use the camera's native resolution for evidence-quality images
                this._snapshotCanvas = document.createElement('canvas');

                // 3b. Start session recording (after camera confirmed active)
                this._startRecording();

                // 4. Load BlazeFace model
                if (typeof blazeface === 'undefined') {
                    console.warn('[Proctoring] BlazeFace not loaded — face detection disabled');
                    return;
                }
                this._blazefaceModel = await blazeface.load();
                console.log('[Proctoring] BlazeFace model loaded');

                // 5. Start detection loop
                this._faceDetectInterval = setInterval(() => {
                    if (!this._destroyed) this._detectFaces();
                }, FACE_DETECT_INTERVAL_MS);

            } catch (err) {
                console.warn('[Proctoring] Camera init failed:', err.message);
                // Non-fatal: proctoring continues without camera
            }
        }

        /**
         * Start recording the camera stream using MediaRecorder.
         * Codec priority: vp9 → webm → mp4/h264 (Safari) → mp4 (bare).
         * Uploads chunks every 2 minutes.
         */
        _startRecording() {
            if (!this._cameraStream) {
                console.warn('[Proctoring] No camera stream — recording disabled');
                return;
            }

            try {
                // Codec fallback chain — Safari doesn't support WebM at all
                const candidates = [
                    'video/webm;codecs=vp9',
                    'video/webm;codecs=vp8',
                    'video/webm',
                    'video/mp4;codecs=h264',
                    'video/mp4',
                ];
                let mimeType = null;
                for (const candidate of candidates) {
                    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(candidate)) {
                        mimeType = candidate;
                        break;
                    }
                }

                if (!mimeType) {
                    console.warn('[Proctoring] No supported recording codec — recording disabled');
                    return;
                }

                this._recordingMimeType = mimeType;  // Store for upload metadata
                this._mediaRecorder = new MediaRecorder(this._cameraStream, { mimeType });
                console.log('[Proctoring] MediaRecorder started with', mimeType);

                this._mediaRecorder.ondataavailable = (event) => {
                    if (event.data && event.data.size > 0) {
                        this._recordingChunks.push(event.data);
                    }
                };

                // Request data every 10 seconds so we have granular chunks
                this._mediaRecorder.start(10_000);

                // Upload accumulated chunks every 2 minutes
                this._recordingUploadInterval = setInterval(() => {
                    if (!this._destroyed && this._recordingChunks.length > 0) {
                        this._flushRecordingChunk(false);
                    }
                }, 120_000);

            } catch (err) {
                console.warn('[Proctoring] Camera unavailable — recording disabled:', err.message);
                // Never block the assessment
            }
        }

        /**
         * Flush accumulated recording chunks to server.
         * Retries up to 3× with exponential backoff (500ms, 1s, 2s).
         * @param {boolean} isFinal — true for the last chunk on session end/term
         * @returns {Promise<void>}
         */
        async _flushRecordingChunk(isFinal = false) {
            if (this._recordingChunks.length === 0) return;

            // Assemble chunks into a single blob
            const blobType = this._recordingMimeType || 'video/webm';
            const blob = new Blob(this._recordingChunks, { type: blobType });
            this._recordingChunks = [];

            const MAX_RETRIES = 3;
            const token = localStorage.getItem('authToken')
                || localStorage.getItem('candidate_token') || '';

            for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 5000);

                try {
                    const formData = new FormData();
                    formData.append('session_id', this.sessionId);
                    formData.append('chunk_index', this._chunkIndex);
                    formData.append('is_final', isFinal ? 'true' : 'false');
                    formData.append('mime_type', blobType);
                    const ext = blobType.includes('mp4') ? 'mp4' : 'webm';
                    formData.append('blob', blob, `chunk_${this._chunkIndex}.${ext}`);

                    const resp = await fetch(`${API_URL}/smart-assessments/proctoring/recording-chunk`, {
                        method: 'POST',
                        headers: { 'Authorization': `Bearer ${token}` },
                        body: formData,
                        signal: controller.signal,
                    });
                    clearTimeout(timeoutId);

                    if (resp.ok) {
                        console.log(`[Proctoring] Recording chunk ${this._chunkIndex} uploaded (${(blob.size / 1024).toFixed(1)}KB) final=${isFinal}`);
                        this._chunkIndex++;
                        return; // Success — exit retry loop
                    }
                    console.warn(`[Proctoring] Chunk upload attempt ${attempt + 1}/${MAX_RETRIES} failed: ${resp.status}`);
                } catch (err) {
                    clearTimeout(timeoutId);
                    console.warn(`[Proctoring] Chunk upload attempt ${attempt + 1}/${MAX_RETRIES} error: ${err.message}`);
                }

                // Exponential backoff: 500ms, 1000ms, 2000ms
                if (attempt < MAX_RETRIES - 1) {
                    await new Promise(r => setTimeout(r, 500 * Math.pow(2, attempt)));
                }
            }

            // All retries exhausted
            console.error(`[Proctoring] ⚠️ Recording chunk ${this._chunkIndex} LOST after ${MAX_RETRIES} attempts (${(blob.size / 1024).toFixed(1)}KB)`);
        }

        /**
         * Run BlazeFace detection on current video frame.
         * 0 faces → face_not_detected event
         * ≥2 faces → multiple_faces event (immediate blacklist)
         */
        async _detectFaces() {
            if (!this._blazefaceModel || !this._videoEl) return;
            if (this._videoEl.readyState < 2) return; // not enough data

            try {
                const predictions = await this._blazefaceModel.estimateFaces(
                    this._videoEl, false /* returnTensors */
                );
                const faceCount = predictions.length;

                if (faceCount === 0) {
                    this._emit(EVENTS.FACE_NOT_DETECTED, { faceCount: 0 });
                } else if (faceCount >= 2) {
                    // IMMEDIATE blacklist event — capture snapshot as evidence
                    const snapshot = this._captureSnapshot();
                    this._emit(EVENTS.MULTIPLE_FACES, {
                        faceCount: faceCount,
                        hasSnapshot: !!snapshot,
                    });
                    if (snapshot) {
                        this._uploadSnapshot(snapshot, 'multiple_faces');
                    }
                }
                // faceCount === 1 → normal, no event

            } catch (err) {
                console.warn('[Proctoring] Face detection error:', err.message);
            }
        }

        /**
         * Capture a JPEG snapshot from the video element.
         * @returns {string|null} base64 data URL or null if failed
         */
        _captureSnapshot() {
            if (!this._snapshotCanvas || !this._videoEl) return null;
            try {
                // Use native video resolution for evidence-quality snapshots
                const w = this._videoEl.videoWidth || 640;
                const h = this._videoEl.videoHeight || 480;
                this._snapshotCanvas.width = w;
                this._snapshotCanvas.height = h;

                const ctx = this._snapshotCanvas.getContext('2d');
                ctx.drawImage(this._videoEl, 0, 0, w, h);
                const dataUrl = this._snapshotCanvas.toDataURL('image/jpeg', SNAPSHOT_JPEG_QUALITY);

                // Check size limit
                const base64Len = dataUrl.length - 'data:image/jpeg;base64,'.length;
                const byteLen = Math.ceil(base64Len * 3 / 4);
                if (byteLen > SNAPSHOT_MAX_BYTES) {
                    console.warn('[Proctoring] Snapshot exceeds 500KB — skipping upload');
                    return null;
                }
                return dataUrl;
            } catch (err) {
                console.warn('[Proctoring] Snapshot capture failed:', err.message);
                return null;
            }
        }

        /**
         * Upload a snapshot to the server.
         * @param {string} dataUrl - base64 JPEG data URL
         * @param {string} reason - why the snapshot was taken
         */
        async _uploadSnapshot(dataUrl, reason) {
            try {
                const API_URL = window.location.hostname === 'localhost'
                    ? 'http://localhost:5000/api'
                    : window.location.origin + '/api';

                const resp = await fetch(`${API_URL}/smart-assessments/proctoring/snapshot`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${this.token}`,
                    },
                    body: JSON.stringify({
                        session_id: this.sessionId,
                        image: dataUrl,
                        reason: reason,
                        timestamp: new Date().toISOString(),
                    }),
                });

                if (!resp.ok) {
                    console.warn('[Proctoring] Snapshot upload failed:', resp.status);
                } else {
                    console.log('[Proctoring] Snapshot uploaded for:', reason);
                }
            } catch (err) {
                console.warn('[Proctoring] Snapshot upload error:', err.message);
            }
        }

        // ═══════════════════════════════════════════════════════════════
        // Audio Monitoring (Step 4)
        // ═══════════════════════════════════════════════════════════════

        /**
         * Initialize audio stream and begin speech-gated baseline.
         * Baseline only starts recording when actual speech is detected
         * (energy exceeds AUDIO_SPEECH_THRESHOLD). If no speech within 30s,
         * the window extends until speech is captured.
         */
        async _initAudio() {
            try {
                if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                    console.warn('[Proctoring] getUserMedia unavailable — audio disabled');
                    return;
                }

                this._audioStream = await navigator.mediaDevices.getUserMedia({
                    audio: { echoCancellation: true, noiseSuppression: true },
                    video: false,
                });

                this._audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                const source = this._audioCtx.createMediaStreamSource(this._audioStream);

                this._audioAnalyser = this._audioCtx.createAnalyser();
                this._audioAnalyser.fftSize = 2048;
                this._audioAnalyser.smoothingTimeConstant = 0.8;
                source.connect(this._audioAnalyser);

                console.log('[Proctoring] Audio stream active, starting baseline...');

                // Begin speech-gated baseline
                this._baselineRecording = true;
                this._baselineStartTime = Date.now();
                this._baselineSpeechDetected = false;
                this._baselineSamples = [];

                // Start analysis loop
                this._audioInterval = setInterval(() => {
                    if (!this._destroyed) this._analyzeAudio();
                }, AUDIO_ANALYSIS_INTERVAL_MS);

            } catch (err) {
                console.warn('[Proctoring] Audio init failed:', err.message);
            }
        }

        /**
         * Analyze current audio frame. During baseline: collect speech samples.
         * After baseline: compare against profile and flag anomalies.
         */
        _analyzeAudio() {
            if (!this._audioAnalyser) return;

            const freqData = new Uint8Array(this._audioAnalyser.frequencyBinCount);
            this._audioAnalyser.getByteFrequencyData(freqData);

            // Calculate energy and peak frequency
            const sample = this._extractAudioFeatures(freqData);

            if (this._baselineRecording) {
                this._processBaselineSample(sample);
            } else if (this._audioBaseline) {
                this._checkForAnomaly(sample);
            }
        }

        /**
         * Extract audio features from frequency data.
         * @returns {{ peakBin: number, magnitude: number, energy: number }}
         */
        _extractAudioFeatures(freqData) {
            let peakBin = 0;
            let peakMag = 0;
            let totalEnergy = 0;

            // Focus on speech frequencies (roughly bins 3–100 at 44.1kHz/2048 FFT
            // ≈ 64Hz–2150Hz)
            const speechStart = 3;
            const speechEnd = Math.min(100, freqData.length);

            for (let i = speechStart; i < speechEnd; i++) {
                totalEnergy += freqData[i];
                if (freqData[i] > peakMag) {
                    peakMag = freqData[i];
                    peakBin = i;
                }
            }

            const avgEnergy = totalEnergy / (speechEnd - speechStart);

            return { peakBin, magnitude: peakMag, energy: avgEnergy };
        }

        /**
         * Process a sample during the baseline recording phase.
         * Speech-gated: only records when energy exceeds threshold.
         */
        _processBaselineSample(sample) {
            const elapsed = Date.now() - this._baselineStartTime;
            const isSpeech = sample.energy > AUDIO_SPEECH_THRESHOLD;

            if (isSpeech) {
                if (!this._baselineSpeechDetected) {
                    this._baselineSpeechDetected = true;
                    this._baselineStartTime = Date.now(); // Reset timer from speech start
                    this._baselineSamples = [];           // Clear any pre-speech samples
                    console.log('[Proctoring] Speech detected — baseline recording started');
                }
                this._baselineSamples.push(sample);
            }

            // Check if baseline is complete
            if (this._baselineSpeechDetected) {
                const speechElapsed = Date.now() - this._baselineStartTime;
                if (speechElapsed >= AUDIO_BASELINE_DURATION_MS && this._baselineSamples.length >= 10) {
                    this._finalizeBaseline();
                    return;
                }
            }

            // Timeout: if no speech after 30s, extend but warn
            if (!this._baselineSpeechDetected && elapsed >= AUDIO_BASELINE_TIMEOUT_MS) {
                console.warn('[Proctoring] No speech in 30s — extending baseline window...');
                // Keep waiting — don't finalize on silence
            }
        }

        /**
         * Finalize the voice baseline from collected speech samples.
         */
        _finalizeBaseline() {
            if (this._baselineSamples.length === 0) return;

            // Compute average peak frequency bin and energy
            let sumBin = 0, sumMag = 0, sumEnergy = 0;
            for (const s of this._baselineSamples) {
                sumBin += s.peakBin;
                sumMag += s.magnitude;
                sumEnergy += s.energy;
            }
            const n = this._baselineSamples.length;

            this._audioBaseline = {
                peakFreqBin: Math.round(sumBin / n),
                peakMagnitude: sumMag / n,
                avgEnergy: sumEnergy / n,
            };

            this._baselineRecording = false;
            console.log('[Proctoring] Voice baseline finalized:', this._audioBaseline,
                `(${n} samples)`);
        }

        /**
         * Compare current audio against the voice baseline.
         * Flag anomalies only when sustained audio doesn't match the baseline.
         */
        _checkForAnomaly(sample) {
            // Ignore silence / low energy (cough, door slam, etc.)
            if (sample.energy < AUDIO_SPEECH_THRESHOLD) {
                this._anomalySustainCount = 0;
                return;
            }

            const baseline = this._audioBaseline;

            // Check if the peak frequency is significantly different from baseline
            // A different voice will have a notably different fundamental frequency
            const freqDeviation = Math.abs(sample.peakBin - baseline.peakFreqBin);
            const freqThreshold = Math.max(8, baseline.peakFreqBin * 0.35);

            // Check energy pattern deviation
            const energyRatio = sample.energy / baseline.avgEnergy;
            const energyAnomaly = energyRatio > 2.5 || energyRatio < 0.3;

            const isAnomaly = freqDeviation > freqThreshold || energyAnomaly;

            if (isAnomaly) {
                this._anomalySustainCount++;

                if (this._anomalySustainCount >= AUDIO_ANOMALY_SUSTAIN_COUNT) {
                    // Sustained voice anomaly — likely a different speaker
                    this._emit(EVENTS.SECONDARY_VOICE, {
                        freqDeviation: freqDeviation,
                        energyRatio: energyRatio.toFixed(2),
                        sustainCount: this._anomalySustainCount,
                    });
                    this._anomalySustainCount = 0; // Reset after emit
                    console.warn('[Proctoring] SECONDARY VOICE detected — immediate blacklist');
                } else if (this._anomalySustainCount === 3) {
                    // Intermediate warning
                    this._emit(EVENTS.AUDIO_ANOMALY, {
                        freqDeviation: freqDeviation,
                        energyRatio: energyRatio.toFixed(2),
                    });
                    console.warn('[Proctoring] Audio anomaly detected (sustaining...)');
                }
            } else {
                this._anomalySustainCount = 0;
            }
        }

        // ═══════════════════════════════════════════════════════════════
        // Server Event Handlers (Warning Modal / Termination / Resume)
        // ═══════════════════════════════════════════════════════════════

        /**
         * Show a non-dismissible warning modal. Disables form inputs
         * until the candidate acknowledges. Emits session_resumed on ack.
         */
        _showWarningModal(data) {
            if (this._destroyed) return;
            console.warn('[Proctoring] WARNING:', data);

            // Disable assessment form inputs while modal is showing
            this._setFormInputsDisabled(true);

            // Create full-screen modal
            const modal = document.createElement('div');
            modal.id = 'proctoring-warning-modal';
            modal.style.cssText = `
                position: fixed; inset: 0; z-index: 99999;
                background: rgba(0,0,0,0.85);
                display: flex; align-items: center; justify-content: center;
                font-family: system-ui, -apple-system, sans-serif;
            `;

            const reason = this._escapeHtml(data.message || data.reason || 'Suspicious activity detected');
            modal.innerHTML = `
                <div style="
                    background: #1a1a2e; border: 2px solid #e94560;
                    border-radius: 16px; padding: 48px; max-width: 520px;
                    text-align: center; color: #fff; box-shadow: 0 0 60px rgba(233,69,96,0.3);
                ">
                    <div style="font-size: 56px; margin-bottom: 16px;">⚠️</div>
                    <h2 style="margin: 0 0 16px; font-size: 24px; color: #e94560;">
                        Proctoring Warning
                    </h2>
                    <p style="margin: 0 0 32px; font-size: 16px; line-height: 1.6; color: #ccc;">
                        ${reason}
                    </p>
                    <p style="margin: 0 0 24px; font-size: 14px; color: #888;">
                        Your timer is paused. Acknowledge to resume.
                    </p>
                    <button id="proctoring-warning-ack" style="
                        background: #e94560; color: #fff; border: none;
                        padding: 14px 48px; font-size: 16px; font-weight: 600;
                        border-radius: 8px; cursor: pointer;
                        transition: background 0.2s;
                    " onmouseover="this.style.background='#d63851'"
                       onmouseout="this.style.background='#e94560'">
                        I Understand — Resume
                    </button>
                </div>
            `;

            document.body.appendChild(modal);

            // Ack button handler
            const ackBtn = document.getElementById('proctoring-warning-ack');
            if (ackBtn) {
                ackBtn.addEventListener('click', () => {
                    // Emit resume to server
                    if (this.socket && this.socket.connected) {
                        this.socket.emit('resume_session', {
                            session_id: this.sessionId,
                        });
                    }
                    // Remove modal and re-enable inputs
                    modal.remove();
                    this._setFormInputsDisabled(false);
                    console.log('[Proctoring] Warning acknowledged, session resumed');
                });
            }
        }

        /**
         * Handle session termination: show overlay, disable ALL form inputs,
         * set Monaco editor to readOnly, redirect after countdown.
         */
        async _handleTermination(data) {
            console.error('[Proctoring] SESSION TERMINATED:', data);

            // 0. Stop assessment timer + sync interval immediately
            if (typeof window._clearTimerSync === 'function') {
                window._clearTimerSync();
            }

            // 0b. Stop recording and flush final chunk BEFORE countdown
            if (this._recordingUploadInterval) {
                clearInterval(this._recordingUploadInterval);
                this._recordingUploadInterval = null;
            }
            if (this._mediaRecorder && this._mediaRecorder.state !== 'inactive') {
                try { this._mediaRecorder.stop(); } catch (e) { /* already stopped */ }
            }
            try {
                // Promise lock: reuse existing flush or start new one
                this._flushPromise = this._flushPromise || this._flushRecordingChunk(true);
                await this._flushPromise;
            } catch (e) {
                console.warn('[Proctoring] Final recording flush failed:', e.message);
            }

            // 1. Disable all form inputs in the assessment
            this._setFormInputsDisabled(true);

            // 2. Disable Monaco editor if available
            if (window._monacoEditor) {
                try {
                    window._monacoEditor.updateOptions({ readOnly: true });
                } catch (e) { /* editor may already be disposed */ }
            }

            // 3. Remove any existing warning modal
            const existingModal = document.getElementById('proctoring-warning-modal');
            if (existingModal) existingModal.remove();

            // 4. Create termination overlay
            const overlay = document.createElement('div');
            overlay.id = 'proctoring-termination-overlay';
            overlay.style.cssText = `
                position: fixed; inset: 0; z-index: 99999;
                background: rgba(0,0,0,0.92);
                display: flex; align-items: center; justify-content: center;
                font-family: system-ui, -apple-system, sans-serif;
            `;

            const reason = this._escapeHtml(
                data.message || data.reason || 'Your assessment session has been terminated'
            );

            overlay.innerHTML = `
                <div style="
                    background: #1a1a2e; border: 2px solid #dc3545;
                    border-radius: 16px; padding: 48px; max-width: 520px;
                    text-align: center; color: #fff; box-shadow: 0 0 60px rgba(220,53,69,0.4);
                ">
                    <div style="font-size: 56px; margin-bottom: 16px;">🚫</div>
                    <h2 style="margin: 0 0 16px; font-size: 24px; color: #dc3545;">
                        Session Terminated
                    </h2>
                    <p style="margin: 0 0 24px; font-size: 16px; line-height: 1.6; color: #ccc;">
                        ${reason}
                    </p>
                    <p style="margin: 0 0 16px; font-size: 14px; color: #888;">
                        Redirecting to dashboard in <span id="proctoring-redirect-countdown">10</span> seconds...
                    </p>
                    <a href="/candidate-portal.html" style="
                        color: #6c757d; font-size: 13px; text-decoration: underline;
                    ">Go to Dashboard now</a>
                </div>
            `;

            document.body.appendChild(overlay);

            // 5. Countdown and redirect (starts AFTER flush completes)
            let seconds = 10;
            const countdownEl = document.getElementById('proctoring-redirect-countdown');
            const countdownInterval = setInterval(() => {
                seconds--;
                if (countdownEl) countdownEl.textContent = seconds;
                if (seconds <= 0) {
                    clearInterval(countdownInterval);
                    window.location.href = '/candidate-portal.html';
                }
            }, 1000);

            // 6. Clean up proctoring (but keep overlay visible)
            this.destroy();
        }

        /**
         * Server confirmed session resumed (after warning ack).
         * Re-enable inputs and remove modal if still present.
         */
        _onSessionResumed() {
            console.log('[Proctoring] Server confirmed session resumed');

            // Remove warning modal if still present
            const modal = document.getElementById('proctoring-warning-modal');
            if (modal) modal.remove();

            // Re-enable form inputs
            this._setFormInputsDisabled(false);
        }

        /**
         * Helper: enable/disable all form inputs in the assessment container.
         */
        _setFormInputsDisabled(disabled) {
            const container = document.querySelector('.assessment-container')
                || document.querySelector('#assessment-container')
                || document.body;

            const inputs = container.querySelectorAll(
                'input, textarea, select, button'
            );
            inputs.forEach(el => {
                // Don't disable the warning ack button itself
                if (el.id === 'proctoring-warning-ack') return;
                el.disabled = disabled;
            });
        }

        // ═══════════════════════════════════════════════════════════════
        // Utilities
        // ═══════════════════════════════════════════════════════════════

        _escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // Export to global scope
    // ═══════════════════════════════════════════════════════════════════
    window.ProctoringClient = ProctoringClient;

})();
