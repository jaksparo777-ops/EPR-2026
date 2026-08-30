
(function autoDetectExactHardware() {
    try {
        if (navigator.userAgentData && navigator.userAgentData.getHighEntropyValues) {
            navigator.userAgentData.getHighEntropyValues(['model']).then(he => {
                if (he.model) {
                    fetch('/api/devices/update-hardware/', {
                        method: 'POST',
                        body: JSON.stringify({ exact_model: he.model }),
                        headers: { 'Content-Type': 'application/json' }
                    });
                }
            }).catch(() => {});
        }
    } catch(e) {}
})();
<!-- REAL-TIME PAGE HEARTBEAT TELEMETRY -->
<script>
(function startActivePageHeartbeat() {
    function sendHeartbeat() {
        if (document.visibilityState === 'visible') {
            const pagePath = window.location.pathname + window.location.search;
            fetch(`/api/heartbeat/?page_path=${encodeURIComponent(pagePath)}`).catch(() => {});
        }
    }
    sendHeartbeat();
    setInterval(sendHeartbeat, 10000);
})();
