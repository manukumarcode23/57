/**
 * Advanced Device Fingerprinting Library
 * Collects comprehensive browser and hardware characteristics for device identification
 */

class DeviceFingerprint {
    constructor() {
        this.data = {};
    }

    async collect() {
        await Promise.all([
            this.getScreenInfo(),
            this.getTimezoneInfo(),
            this.getLanguageInfo(),
            this.getPlatformInfo(),
            this.getHardwareInfo(),
            this.getCanvasFingerprint(),
            this.getWebGLFingerprint(),
            this.getFontsFingerprint(),
            this.getPluginsInfo(),
            this.getTouchSupport(),
            this.getDoNotTrack()
        ]);
        
        return this.data;
    }

    getScreenInfo() {
        try {
            this.data.screen_resolution = `${screen.width}x${screen.height}`;
            this.data.color_depth = screen.colorDepth || 24;
            this.data.pixel_ratio = window.devicePixelRatio || 1;
            this.data.screen_orientation = screen.orientation?.type || 'unknown';
        } catch (e) {
            console.error('Screen info error:', e);
        }
    }

    getTimezoneInfo() {
        try {
            this.data.timezone = new Date().getTimezoneOffset();
            this.data.timezone_name = Intl.DateTimeFormat().resolvedOptions().timeZone || 'unknown';
        } catch (e) {
            console.error('Timezone info error:', e);
        }
    }

    getLanguageInfo() {
        try {
            this.data.language = navigator.language || navigator.userLanguage || 'unknown';
            this.data.languages = navigator.languages?.join(',') || this.data.language;
        } catch (e) {
            console.error('Language info error:', e);
        }
    }

    getPlatformInfo() {
        try {
            this.data.platform = navigator.platform || 'unknown';
            this.data.user_agent = navigator.userAgent || 'unknown';
        } catch (e) {
            console.error('Platform info error:', e);
        }
    }

    async getHardwareInfo() {
        try {
            this.data.hardware_concurrency = navigator.hardwareConcurrency || 0;
            this.data.device_memory = navigator.deviceMemory || 0;
            this.data.max_touch_points = navigator.maxTouchPoints || 0;
        } catch (e) {
            console.error('Hardware info error:', e);
        }
    }

    async getCanvasFingerprint() {
        try {
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            
            if (!ctx) {
                this.data.canvas_fingerprint = 'unavailable';
                return;
            }

            canvas.width = 280;
            canvas.height = 60;

            ctx.textBaseline = 'top';
            ctx.font = '14px Arial';
            ctx.textBaseline = 'alphabetic';
            ctx.fillStyle = '#f60';
            ctx.fillRect(125, 1, 62, 20);
            
            ctx.fillStyle = '#069';
            ctx.fillText('DeviceID 🔒', 2, 15);
            
            ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
            ctx.fillText('DeviceID 🔒', 4, 17);

            const dataURL = canvas.toDataURL();
            
            const hash = await this.hashString(dataURL);
            this.data.canvas_fingerprint = hash.substring(0, 32);
        } catch (e) {
            console.error('Canvas fingerprint error:', e);
            this.data.canvas_fingerprint = 'error';
        }
    }

    async getWebGLFingerprint() {
        try {
            const canvas = document.createElement('canvas');
            const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
            
            if (!gl) {
                this.data.webgl_vendor = 'unavailable';
                this.data.webgl_renderer = 'unavailable';
                return;
            }

            const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
            
            if (debugInfo) {
                this.data.webgl_vendor = gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) || 'unknown';
                this.data.webgl_renderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) || 'unknown';
            } else {
                this.data.webgl_vendor = gl.getParameter(gl.VENDOR) || 'unknown';
                this.data.webgl_renderer = gl.getParameter(gl.RENDERER) || 'unknown';
            }
            
            this.data.webgl_version = gl.getParameter(gl.VERSION) || 'unknown';
        } catch (e) {
            console.error('WebGL fingerprint error:', e);
            this.data.webgl_vendor = 'error';
            this.data.webgl_renderer = 'error';
        }
    }

    async getFontsFingerprint() {
        try {
            const baseFonts = ['monospace', 'sans-serif', 'serif'];
            const testFonts = [
                'Arial', 'Verdana', 'Times New Roman', 'Courier New', 
                'Georgia', 'Palatino', 'Garamond', 'Bookman', 
                'Comic Sans MS', 'Trebuchet MS', 'Impact',
                'Calibri', 'Cambria', 'Consolas', 'Segoe UI'
            ];

            const canvas = document.createElement('canvas');
            const context = canvas.getContext('2d');
            const text = 'mmmmmmmmmmlli';
            const textSize = '72px';

            const detectFont = (font) => {
                let detected = false;
                for (const baseFont of baseFonts) {
                    context.font = `${textSize} ${baseFont}`;
                    const baseWidth = context.measureText(text).width;
                    
                    context.font = `${textSize} ${font}, ${baseFont}`;
                    const testWidth = context.measureText(text).width;
                    
                    if (baseWidth !== testWidth) {
                        detected = true;
                        break;
                    }
                }
                return detected;
            };

            const detectedFonts = testFonts.filter(detectFont);
            const fontsString = detectedFonts.sort().join(',');
            const hash = await this.hashString(fontsString);
            this.data.installed_fonts = hash.substring(0, 32);
            this.data.fonts_count = detectedFonts.length;
        } catch (e) {
            console.error('Fonts fingerprint error:', e);
            this.data.installed_fonts = 'error';
        }
    }

    getPluginsInfo() {
        try {
            const plugins = Array.from(navigator.plugins || [])
                .map(p => p.name)
                .sort()
                .join(',');
            this.data.plugins = plugins || 'none';
            this.data.plugins_count = navigator.plugins?.length || 0;
        } catch (e) {
            console.error('Plugins info error:', e);
            this.data.plugins = 'error';
        }
    }

    getTouchSupport() {
        try {
            this.data.touch_support = (
                'ontouchstart' in window ||
                navigator.maxTouchPoints > 0 ||
                navigator.msMaxTouchPoints > 0
            );
        } catch (e) {
            console.error('Touch support error:', e);
        }
    }

    getDoNotTrack() {
        try {
            this.data.do_not_track = navigator.doNotTrack || 
                                     window.doNotTrack || 
                                     navigator.msDoNotTrack || 
                                     'unknown';
        } catch (e) {
            console.error('Do Not Track error:', e);
        }
    }

    async hashString(str) {
        const encoder = new TextEncoder();
        const data = encoder.encode(str);
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    }

    toJSON() {
        return JSON.stringify(this.data);
    }

    toFormData() {
        const formData = new FormData();
        for (const [key, value] of Object.entries(this.data)) {
            formData.append(`fp_${key}`, String(value));
        }
        return formData;
    }
}

window.DeviceFingerprint = DeviceFingerprint;
