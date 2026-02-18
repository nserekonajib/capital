// Custom YouTube Player - Enhanced Version
class CSPlayer {
    static instances = new Map();
    
    constructor(videoTag, params = {}) {
        if (!videoTag || !params.defaultId) {
            throw new Error('videoTag and params.defaultId are required');
        }
        
        if (CSPlayer.instances.has(videoTag)) {
            throw new Error(`Player ${videoTag} already exists`);
        }
        
        this.videoTag = videoTag;
        this.params = {
            defaultId: params.defaultId,
            loop: params.loop || false,
            thumbnail: params.thumbnail || true,
            theme: params.theme || null,
            autoplay: params.autoplay || true
        };
        
        this.player = null;
        this.isPlaying = false;
        this.playerState = 'paused';
        this.initialized = false;
        this.intervals = new Set();
        this.controlsTimeout = null;
        this.dom = {};
        
        CSPlayer.instances.set(videoTag, this);
    }
    
    // DOM utility function
    static $(selector, parent = document) {
        const elements = parent.querySelectorAll(selector);
        return elements.length === 1 ? elements[0] : elements.length === 0 ? null : elements;
    }
    
    // Format seconds to time string
    static formatTime(seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        
        return h > 0 
            ? `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
            : `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }
    
    // Create player HTML structure
    createPlayerHTML() {
        const themeClass = this.params.theme ? `theme-${this.params.theme}` : '';
        const playerTagId = `csPlayer-${this.videoTag}`;
        
        return `
            <div class="csPlayer ${themeClass}">
                <div class="csPlayer-container">
                    <span class="csPlayer-thumbnail">
                        <div></div>
                        <i class="ti ti-player-play-filled csPlayer-loading"></i>
                        <div></div>
                    </span>
                    <div id="${playerTagId}" class="csPlayer-iframe-container"></div>
                </div>
                <div class="csPlayer-controls-box">
                    <main class="csPlayer-main-controls">
                        <i class="ti ti-rewind-backward-10" data-action="backward"></i>
                        <i class="ti csPlayer-play-pause-btn ti-player-play-filled" data-action="play-pause"></i>
                        <i class="ti ti-rewind-forward-10" data-action="forward"></i>
                    </main>
                    <div class="csPlayer-controls">
                        <p class="csPlayer-current-time">00:00</p>
                        <div class="csPlayer-progress">
                            <span class="csPlayer-loaded"></span>
                            <input type="range" class="csPlayer-slider" min="0" max="100" value="0" step="1">
                        </div>
                        <p class="csPlayer-duration">00:00</p>
                        <i class="ti ti-settings csPlayer-settings-btn" data-action="settings"></i>
                        <i class="ti ti-maximize csPlayer-fullscreen-btn" data-action="fullscreen"></i>
                    </div>
                    <div class="csPlayer-settings-box">
                        <p class="csPlayer-settings-item" data-setting="speed">
                            Speed<b>1x</b><i class="ti ti-caret-right-filled"></i>
                        </p>
                        <span class="csPlayer-settings-options" data-options="speed">     
                            <label><input type="radio" name="${this.videoTag}-speed" value="0.75">0.75x</label>
                            <label><input type="radio" name="${this.videoTag}-speed" value="1" checked>1x</label>
                            <label><input type="radio" name="${this.videoTag}-speed" value="1.25">1.25x</label>
                            <label><input type="radio" name="${this.videoTag}-speed" value="1.5">1.5x</label>
                            <label><input type="radio" name="${this.videoTag}-speed" value="1.75">1.75x</label>
                            <label><input type="radio" name="${this.videoTag}-speed" value="2">2x</label>
                        </span>
                        <p class="csPlayer-settings-item" data-setting="quality">
                            Quality<b>auto</b><i class="ti ti-caret-right-filled"></i>
                        </p>
                        <span class="csPlayer-settings-options" data-options="quality">
                            <label><input type="radio" name="${this.videoTag}-quality" value="auto" checked>auto</label>
                        </span>
                    </div>
                </div>
            </div>
        `;
    }
    
    // Initialize the player
    async init() {
        const container = CSPlayer.$(`#${this.videoTag}`);
        if (!container) {
            throw new Error(`Container #${this.videoTag} not found`);
        }
        
        // Create player structure
        container.innerHTML = this.createPlayerHTML();
        
        // Cache DOM elements
        this.cacheDOMElements();
        
        // Setup thumbnail
        this.setupThumbnail();
        
        // Initialize YouTube player
        await this.initYouTubePlayer();
        
        // Setup event listeners
        this.setupEventListeners();
        
        this.initialized = true;
        console.log(`Player ${this.videoTag} initialized successfully`);
    }
    
    // Cache frequently used DOM elements
    cacheDOMElements() {
        const parent = CSPlayer.$(`#${this.videoTag} .csPlayer`);
        this.dom = {
            parent,
            container: CSPlayer.$('.csPlayer-container', parent),
            controlsBox: CSPlayer.$('.csPlayer-controls-box', parent),
            mainControls: CSPlayer.$('.csPlayer-main-controls', parent),
            playPauseBtn: CSPlayer.$('.csPlayer-play-pause-btn', parent),
            currentTime: CSPlayer.$('.csPlayer-current-time', parent),
            duration: CSPlayer.$('.csPlayer-duration', parent),
            slider: CSPlayer.$('.csPlayer-slider', parent),
            loaded: CSPlayer.$('.csPlayer-loaded', parent),
            settingsBox: CSPlayer.$('.csPlayer-settings-box', parent),
            thumbnail: CSPlayer.$('.csPlayer-thumbnail', parent)
        };
    }
    
    // Setup thumbnail
    setupThumbnail() {
        if (this.params.thumbnail === false || this.params.thumbnail === 'false') {
            this.dom.thumbnail.style.backgroundImage = 'none';
        } else if (this.params.thumbnail === true || this.params.thumbnail === 'true') {
            this.dom.thumbnail.style.backgroundImage = 
                `url("https://img.youtube.com/vi/${this.params.defaultId}/maxresdefault.jpg")`;
        } else if (typeof this.params.thumbnail === 'string') {
            this.dom.thumbnail.style.backgroundImage = `url(${this.params.thumbnail})`;
        }
    }
    
    // Initialize YouTube Player
    initYouTubePlayer() {
        return new Promise((resolve, reject) => {
            const playerTagId = `csPlayer-${this.videoTag}`;
            
            this.player = new YT.Player(playerTagId, {
                videoId: this.params.defaultId,
                playerVars: {
                    controls: 0,
                    mute: 1,
                    autoplay: this.params.autoplay ? 1 : 0,
                    disablekb: 1,
                    color: 'white',
                    fs: 0,
                    playsinline: 1,
                    rel: 0,
                    loop: this.params.loop ? 1 : 0,
                    cc_load_policy: 3,
                    showinfo: 0,
                    iv_load_policy: 3,
                },
                events: {
                    onReady: () => {
                        this.onPlayerReady();
                        resolve();
                    },
                    onStateChange: (event) => this.onPlayerStateChange(event),
                    onError: (error) => {
                        console.error('YouTube Player Error:', error);
                        reject(error);
                    }
                }
            });
        });
    }
    
    // Player ready callback
    onPlayerReady() {
        this.dom.thumbnail.querySelector('i').classList.remove('csPlayer-loading');
        
        // Start intervals for UI updates
        this.startIntervals();
        
        // Show fullscreen button if supported
        this.dom.parent.querySelector('.csPlayer-fullscreen-btn').style.display = 
            document.fullscreenEnabled ? 'block' : 'none';
    }
    
    // Start update intervals
    startIntervals() {
        const textTimeInterval = setInterval(() => this.updateTextTime(), 1000);
        const timeSliderInterval = setInterval(() => this.updateTimeSlider(), 1000);
        
        this.intervals.add(textTimeInterval);
        this.intervals.add(timeSliderInterval);
    }
    
    // Setup event listeners
    setupEventListeners() {
        // Main controls
        this.dom.mainControls.addEventListener('click', (e) => {
            const action = e.target.closest('[data-action]')?.dataset.action;
            this.handleControlAction(action);
        });
        
        // Progress slider
        this.dom.slider.addEventListener('input', () => this.handleSliderInput());
        
        // Settings
        this.dom.settingsBox.addEventListener('click', (e) => {
            const action = e.target.closest('[data-action]')?.dataset.action;
            if (action === 'settings') {
                this.toggleSettings();
            }
        });
        
        // Settings items
        this.dom.settingsBox.addEventListener('click', (e) => {
            const settingItem = e.target.closest('[data-setting]');
            if (settingItem) {
                this.toggleSettingsOption(settingItem.dataset.setting);
            }
        });
        
        // Settings options
        this.setupSettingsOptions();
        
        // Controls box interactions
        this.setupControlsInteractions();
    }
    
    // Handle control actions
    handleControlAction(action) {
        this.resetControlsTimeout();
        
        switch (action) {
            case 'backward':
                this.seek(-10);
                break;
            case 'forward':
                this.seek(10);
                break;
            case 'play-pause':
                this.togglePlayPause();
                break;
        }
    }
    
    // Seek forward/backward
    seek(seconds) {
        const currentTime = this.player.getCurrentTime();
        this.player.seekTo(Math.max(0, currentTime + seconds), true);
        this.updateUI();
    }
    
    // Toggle play/pause
    togglePlayPause() {
        if (this.isPlaying) {
            this.pause();
        } else {
            this.play();
        }
    }
    
    // Play video
    play() {
        this.player.playVideo();
        this.resetControlsTimeout(3000);
    }
    
    // Pause video
    pause() {
        this.player.pauseVideo();
        this.showControls();
    }
    
    // Handle slider input
    handleSliderInput() {
        this.resetControlsTimeout();
        const duration = this.player.getDuration();
        const progress = this.dom.slider.value;
        
        this.player.seekTo((progress / 100) * duration);
        this.updateSliderStyle(progress);
    }
    
    // Update slider visual style
    updateSliderStyle(progress) {
        this.dom.slider.style.background = 
            `linear-gradient(to right, var(--sliderSeekTrackColor) ${progress}%, transparent ${progress}%)`;
    }
    
    // Update text time display
    updateTextTime() {
        if (!this.player || !this.player.getCurrentTime) return;
        
        const currentTime = this.player.getCurrentTime();
        const duration = this.player.getDuration();
        
        this.dom.currentTime.textContent = CSPlayer.formatTime(currentTime);
        this.dom.duration.textContent = CSPlayer.formatTime(duration);
    }
    
    // Update time slider
    updateTimeSlider() {
        if (!this.player || !this.player.getCurrentTime) return;
        
        const currentTime = this.player.getCurrentTime();
        const duration = this.player.getDuration();
        const progress = (currentTime / duration) * 100;
        const loaded = (this.player.getVideoLoadedFraction() || 0) * 100;
        
        this.dom.slider.value = progress;
        this.dom.loaded.style.width = `${loaded}%`;
        this.updateSliderStyle(progress);
    }
    
    // Update UI elements
    updateUI() {
        this.updateTextTime();
        this.updateTimeSlider();
    }
    
    // Player state change handler
    onPlayerStateChange(event) {
        switch (event.data) {
            case YT.PlayerState.PLAYING:
                this.handlePlayingState();
                break;
            case YT.PlayerState.PAUSED:
                this.handlePausedState();
                break;
            case YT.PlayerState.ENDED:
                this.handleEndedState();
                break;
            case YT.PlayerState.BUFFERING:
                this.playerState = 'buffering';
                break;
            case YT.PlayerState.CUED:
                this.playerState = 'cued';
                break;
        }
        
        // Try to unload captions modules
        try {
            this.player.unloadModule('captions');
            this.player.unloadModule('cc');
        } catch (error) {
            // Silent fail - not critical
        }
    }
    
    // Handle playing state
    handlePlayingState() {
        this.isPlaying = true;
        this.playerState = 'playing';
        this.dom.playPauseBtn.className = 'ti csPlayer-play-pause-btn ti-player-pause-filled';
        this.dom.thumbnail.querySelector('i').classList.add('csPlayer-loading');
        this.dom.thumbnail.style.display = 'none';
        this.dom.container.style.pointerEvents = 'none';
        this.dom.controlsBox.style.display = 'flex';
        
        this.player.unMute();
        this.resetControlsTimeout(3000);
    }
    
    // Handle paused state
    handlePausedState() {
        this.isPlaying = false;
        this.playerState = 'paused';
        this.dom.playPauseBtn.className = 'ti csPlayer-play-pause-btn ti-player-play-filled';
        this.showControls();
    }
    
    // Handle ended state
    handleEndedState() {
        if (this.params.loop) {
            this.player.seekTo(0);
        } else {
            this.player.seekTo(0);
            this.player.pauseVideo();
            this.playerState = 'ended';
        }
    }
    
    // Setup controls interactions
    setupControlsInteractions() {
        this.dom.controlsBox.addEventListener('click', (e) => {
            if (!this.isControlElement(e.target)) {
                this.toggleControlsVisibility();
            }
        });
        
        this.dom.controlsBox.querySelector('.csPlayer-controls').addEventListener('click', () => {
            this.resetControlsTimeout(3000);
        });
    }
    
    // Check if element is a control element
    isControlElement(element) {
        return element.closest('.csPlayer-main-controls') ||
               element.closest('.csPlayer-controls') ||
               element.closest('.csPlayer-settings-box');
    }
    
    // Toggle controls visibility
    toggleControlsVisibility() {
        if (this.dom.controlsBox.classList.contains('csPlayer-controls-open')) {
            this.hideControls();
        } else {
            this.showControls();
            this.resetControlsTimeout(3000);
        }
    }
    
    // Show controls
    showControls() {
        this.dom.controlsBox.classList.add('csPlayer-controls-open');
    }
    
    // Hide controls
    hideControls() {
        this.dom.controlsBox.classList.remove('csPlayer-controls-open');
    }
    
    // Reset controls timeout
    resetControlsTimeout(delay = 3000) {
        if (this.controlsTimeout) {
            clearTimeout(this.controlsTimeout);
        }
        if (delay > 0) {
            this.controlsTimeout = setTimeout(() => this.hideControls(), delay);
        }
    }
    
    // Toggle settings panel
    toggleSettings() {
        const isVisible = this.dom.settingsBox.style.display === 'block';
        this.dom.settingsBox.style.display = isVisible ? 'none' : 'block';
        
        if (!isVisible) {
            this.populateQualityOptions();
        } else {
            this.resetSettings();
        }
    }
    
    // Toggle specific settings option
    toggleSettingsOption(setting) {
        const allOptions = this.dom.settingsBox.querySelectorAll('[data-options]');
        const targetOptions = this.dom.settingsBox.querySelector(`[data-options="${setting}"]`);
        
        allOptions.forEach(option => {
            option.style.maxHeight = '0px';
        });
        
        if (targetOptions.style.maxHeight === '0px' || !targetOptions.style.maxHeight) {
            targetOptions.style.maxHeight = '400px';
        } else {
            targetOptions.style.maxHeight = '0px';
        }
    }
    
    // Reset settings to default state
    resetSettings() {
        const allOptions = this.dom.settingsBox.querySelectorAll('[data-options]');
        allOptions.forEach(option => {
            option.style.maxHeight = '0px';
        });
    }
    
    // Setup settings options
    setupSettingsOptions() {
        // Playback speed
        const speedInputs = this.dom.settingsBox.querySelectorAll('[name="${this.videoTag}-speed"]');
        speedInputs.forEach(input => {
            input.addEventListener('change', (e) => {
                const value = e.target.value;
                this.dom.settingsBox.querySelector('[data-setting="speed"] b').textContent = value + 'x';
                this.player.setPlaybackRate(Number(value));
            });
        });
        
        // Quality
        const qualityInputs = this.dom.settingsBox.querySelectorAll('[name="${this.videoTag}-quality"]');
        qualityInputs.forEach(input => {
            input.addEventListener('change', (e) => {
                const value = e.target.value;
                this.dom.settingsBox.querySelector('[data-setting="quality"] b').textContent = value;
                this.player.setPlaybackQuality(value);
            });
        });
    }
    
    // Populate quality options
    populateQualityOptions() {
        const qualityContainer = this.dom.settingsBox.querySelector('[data-options="quality"]');
        const qualities = this.player.getAvailableQualityLevels();
        
        qualities.forEach(quality => {
            if (!qualityContainer.innerHTML.includes(quality)) {
                qualityContainer.innerHTML += 
                    `<label><input type="radio" name="${this.videoTag}-quality" value="${quality}">${quality}</label>`;
            }
        });
        
        // Re-attach event listeners
        this.setupSettingsOptions();
    }
    
    // Toggle fullscreen
    toggleFullscreen() {
        const videoContainer = this.dom.parent;
        
        if (!document.fullscreenElement) {
            const requestMethod = videoContainer.requestFullscreen ||
                                videoContainer.mozRequestFullScreen ||
                                videoContainer.webkitRequestFullscreen ||
                                videoContainer.msRequestFullscreen;
            
            if (requestMethod) {
                requestMethod.call(videoContainer);
            }
        } else {
            const exitMethod = document.exitFullscreen ||
                             document.mozCancelFullScreen ||
                             document.webkitExitFullscreen ||
                             document.msExitFullscreen;
            
            if (exitMethod) {
                exitMethod.call(document);
            }
        }
    }
    
    // Public API methods
    async changeVideo(videoId) {
        if (!this.initialized) {
            throw new Error(`Player ${this.videoTag} is not initialized`);
        }
        
        if (this.player.isMuted()) {
            throw new Error('Video must be played at least once before changing');
        }
        
        this.player.loadVideoById(videoId, 0);
        this.params.defaultId = videoId;
        this.setupThumbnail();
    }
    
    getDuration() {
        this.ensureInitialized();
        return this.player.getDuration();
    }
    
    getCurrentTime() {
        this.ensureInitialized();
        return this.player.getCurrentTime();
    }
    
    getVideoTitle() {
        this.ensureInitialized();
        return this.player.getVideoData().title;
    }
    
    getPlayerState() {
        this.ensureInitialized();
        return this.playerState;
    }
    
    // Ensure player is initialized
    ensureInitialized() {
        if (!this.initialized) {
            throw new Error(`Player ${this.videoTag} is not initialized`);
        }
    }
    
    // Destroy player
    destroy() {
        // Clear intervals
        this.intervals.forEach(interval => clearInterval(interval));
        this.intervals.clear();
        
        // Clear timeouts
        if (this.controlsTimeout) {
            clearTimeout(this.controlsTimeout);
        }
        
        // Destroy YouTube player
        if (this.player) {
            this.player.destroy();
        }
        
        // Remove DOM elements
        if (this.dom.parent) {
            this.dom.parent.remove();
        }
        
        // Remove instance
        CSPlayer.instances.delete(this.videoTag);
    }
    
    // Static method to get instance
    static getInstance(videoTag) {
        return CSPlayer.instances.get(videoTag);
    }
    
    // Static method to check if initialized
    static isInitialized(videoTag) {
        const instance = CSPlayer.instances.get(videoTag);
        return instance ? instance.initialized : false;
    }
}

// Global initialization function (backward compatibility)
const csPlayer = {
    csPlayers: {},
    
    init: async (videoTag, params) => {
        try {
            const player = new CSPlayer(videoTag, params);
            await player.init();
            csPlayer.csPlayers[videoTag] = player;
            return player;
        } catch (error) {
            console.error('Failed to initialize player:', error);
            throw error;
        }
    },
    
    pause: (videoTag) => CSPlayer.getInstance(videoTag)?.pause(),
    play: (videoTag) => CSPlayer.getInstance(videoTag)?.play(),
    getDuration: (videoTag) => CSPlayer.getInstance(videoTag)?.getDuration(),
    getCurrentTime: (videoTag) => CSPlayer.getInstance(videoTag)?.getCurrentTime(),
    getVideoTitle: (videoTag) => CSPlayer.getInstance(videoTag)?.getVideoTitle(),
    getPlayerState: (videoTag) => CSPlayer.getInstance(videoTag)?.getPlayerState(),
    changeVideo: (videoTag, videoId) => CSPlayer.getInstance(videoTag)?.changeVideo(videoId),
    destroy: (videoTag) => CSPlayer.getInstance(videoTag)?.destroy(),
    initialized: (videoTag) => CSPlayer.isInitialized(videoTag)
};

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { CSPlayer, csPlayer };
}