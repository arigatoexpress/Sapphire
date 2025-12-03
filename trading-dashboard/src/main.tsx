import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.tsx'
import './index.css'

// Register service worker for PWA and caching
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then((registration) => {
        console.log('SW registered: ', registration);
      })
      .catch((registrationError) => {
        console.log('SW registration failed: ', registrationError);
      });
  });
}

// Handle PWA install prompt
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  // Store for later use if implementing install button
  (window as any).deferredPrompt = e;
  console.log('PWA install prompt available');
});

// Handle online/offline status
window.addEventListener('online', () => {
  console.log('Application is online');
  // Trigger data refresh when coming back online
  window.dispatchEvent(new CustomEvent('app-online'));
});

window.addEventListener('offline', () => {
  console.log('Application is offline');
  // Show offline notification
  if ('Notification' in window && Notification.permission === 'granted') {
    new Notification('Sapphire Trade', {
      body: 'You are currently offline. Some features may be limited.',
      icon: '/sapphire-icon.svg'
    });
  }
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
    <App />
    </BrowserRouter>
  </React.StrictMode>,
)
