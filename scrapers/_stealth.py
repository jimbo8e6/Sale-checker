"""
Injects JavaScript patches into a Playwright page to remove headless-browser
fingerprints that bot-detection systems check for.
"""

_STEALTH_JS = """
// Remove the webdriver flag that all headless browsers expose
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// Fake a real Chrome runtime object
window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}, app: {}};

// Add realistic browser plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const p = [
            {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: ''},
            {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
            {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''}
        ];
        p.__proto__ = PluginArray.prototype;
        return p;
    }
});

// Realistic language list
Object.defineProperty(navigator, 'languages', {get: () => ['en-GB', 'en']});

// Fix permissions API (headless returns denied for notifications by default)
const _origPermQuery = window.navigator.permissions.query.bind(navigator.permissions);
window.navigator.permissions.query = (p) =>
    p.name === 'notifications'
        ? Promise.resolve({state: Notification.permission})
        : _origPermQuery(p);

// Realistic hardware concurrency and memory
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

// Pass the iframe contentWindow check
Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
    get: function() {
        return window;
    }
});
"""


def apply_stealth(page) -> None:
    """Call immediately after page = ctx.new_page()."""
    page.add_init_script(_STEALTH_JS)
