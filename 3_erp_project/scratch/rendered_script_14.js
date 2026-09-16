
(function initInactivityManager() {
    const timeoutMinutes = 60;
    const logoutMode = "POPUP_WARNING";
    
    // Total idle duration in milliseconds
    const totalTimeoutMs = Math.max(60, timeoutMinutes * 60) * 1000;
    const warningLeadSeconds = (totalTimeoutMs > 90000) ? 60 : Math.max(10, Math.floor(timeoutMinutes * 60 * 0.3));
    const warningTriggerMs = Math.max(10000, totalTimeoutMs - (warningLeadSeconds * 1000));
    
    let lastActivityTime = Date.now();
    let isWarningShowing = false;
    let countdownInterval = null;
    let secondsLeft = warningLeadSeconds;
    
    function resetActivity() {
        if (!isWarningShowing) {
            lastActivityTime = Date.now();
        }
    }
    
    // Listen to physical user interactions
    let throttleTimer = null;
    function onUserInteraction() {
        if (!throttleTimer) {
            throttleTimer = setTimeout(() => {
                resetActivity();
                throttleTimer = null;
            }, 1000);
        }
    }
    
    ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'click'].forEach(evt => {
        window.addEventListener(evt, onUserInteraction, { passive: true });
    });
    
    // Poll idle time every second
    setInterval(() => {
        const idleMs = Date.now() - lastActivityTime;
        
        if (logoutMode === 'INSTANT_LOGOUT') {
            if (idleMs >= totalTimeoutMs) {
                performLogout();
            }
        } else {
            if (!isWarningShowing && idleMs >= warningTriggerMs) {
                showWarningModal();
            }
        }
    }, 1000);
    
    function showWarningModal() {
        isWarningShowing = true;
        secondsLeft = Math.max(5, Math.ceil((totalTimeoutMs - (Date.now() - lastActivityTime)) / 1000));
        
        const modal = document.getElementById('inactivityWarningModal');
        const countdownEl = document.getElementById('inactivityCountdownSeconds');
        const durationText = document.getElementById('inactivityDurationText');
        
        if (durationText) durationText.textContent = `${timeoutMinutes} minute${timeoutMinutes > 1 ? 's' : ''}`;
        if (countdownEl) countdownEl.textContent = secondsLeft;
        if (modal) modal.style.display = 'flex';
        
        clearInterval(countdownInterval);
        countdownInterval = setInterval(() => {
            secondsLeft--;
            if (countdownEl) countdownEl.textContent = Math.max(0, secondsLeft);
            if (secondsLeft <= 0) {
                clearInterval(countdownInterval);
                performLogout();
            }
        }, 1000);
    }
    
    window.stayLoggedIn = async function() {
        clearInterval(countdownInterval);
        isWarningShowing = false;
        lastActivityTime = Date.now();
        
        const modal = document.getElementById('inactivityWarningModal');
        if (modal) modal.style.display = 'none';
        
        try {
            await fetch('/api/session/keep-alive/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': 'aKGgTULBNK8ZxFZOF2uaNnV6nlMOUSKWbsMgoz965ANXpw6PnOgkXBpYdZAaHBLG'
                }
            });
        } catch(e) {
            console.warn('Keep alive ping error:', e);
        }
    };
    
    window.inactivitySignOutNow = function() {
        performLogout();
    };
    
    function performLogout() {
        const csrf = 'aKGgTULBNK8ZxFZOF2uaNnV6nlMOUSKWbsMgoz965ANXpw6PnOgkXBpYdZAaHBLG';
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = "/logout/";
        const csrfInput = document.createElement('input');
        csrfInput.type = 'hidden';
        csrfInput.name = 'csrfmiddlewaretoken';
        csrfInput.value = csrf;
        form.appendChild(csrfInput);
        const nextInput = document.createElement('input');
        nextInput.type = 'hidden';
        nextInput.name = 'next';
        nextInput.value = '/login/?reason=timeout';
        form.appendChild(nextInput);
        document.body.appendChild(form);
        form.submit();
    }
})();
