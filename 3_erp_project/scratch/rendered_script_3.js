
    document.addEventListener("DOMContentLoaded", function() {
        const toasts = document.querySelectorAll('.toast');

        toasts.forEach(toast => {
            const close = toast.querySelector('.toast-close');
            const timeout = setTimeout(() => {
                toast.style.opacity = 0;
                setTimeout(() => toast.remove(), 300);
            }, 5000);

            close.addEventListener('click', () => {
                clearTimeout(timeout);
                toast.style.opacity = 0;
                setTimeout(() => toast.remove(), 300);
            });
        });

        // Mobile responsive sidebar toggle controls
        const sidebarToggle = document.getElementById('sidebarToggle');
        const sidebarOverlay = document.getElementById('sidebarOverlay');
        const sidebar = document.querySelector('.sidebar');

        function toggleSidebar() {
            sidebar.classList.toggle('active');
            sidebarOverlay.classList.toggle('active');
        }

        function closeSidebar() {
            sidebar.classList.remove('active');
            sidebarOverlay.classList.remove('active');
        }

        if (sidebarToggle && sidebar && sidebarOverlay) {
            sidebarToggle.addEventListener('click', toggleSidebar);
            sidebarOverlay.addEventListener('click', closeSidebar);

            // Dismiss drawer on escape keypress
            document.addEventListener('keydown', function(event) {
                if (event.key === 'Escape') {
                    closeSidebar();
                }
            });

            // Dismiss drawer on navigation item clicks (useful for mobile SPAs or smooth links)
            const menuLinks = sidebar.querySelectorAll('.menu a');
            menuLinks.forEach(link => {
                link.addEventListener('click', closeSidebar);
            });
        }

        // Globally auto-select all content on focus for text and number inputs
        document.addEventListener('focusin', function(e) {
            if (e.target && e.target.tagName === 'INPUT') {
                const inputType = e.target.type;
                if (inputType === 'number' || inputType === 'text') {
                    setTimeout(() => {
                        if (typeof e.target.select === 'function') {
                            e.target.select();
                        }
                    }, 0);
                }
            }
        });

        // Register PWA Service Worker for Mobile Installation (iOS & Android)
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/static/sw.js').then(function(reg) {
                console.log('Foundry ERP PWA ServiceWorker registered:', reg.scope);
            }).catch(function(err) {
                console.log('PWA ServiceWorker registration failed:', err);
            });
        }
    });
