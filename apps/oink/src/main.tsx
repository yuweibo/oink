import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import 'oink-ui/styles.css';
import './app.css';
import { App } from './App';
import { agent, start } from './api/store';
import { setLanguage } from './i18n';
const settingsPreview=import.meta.env.DEV && new URLSearchParams(location.search).get('fixture')==='settings';
const preview=import.meta.env.DEV && new URLSearchParams(location.search).get('fixture')==='screen-groups';
const hotkeyPreview=import.meta.env.DEV && new URLSearchParams(location.search).get('fixture')==='profile-hotkeys';
if(hotkeyPreview) {
 void import('./arrange/ProfileHotkeyPreview').then(({ProfileHotkeyPreview})=>createRoot(document.getElementById('root')!).render(<StrictMode><ProfileHotkeyPreview/></StrictMode>));
} else if(settingsPreview) {
 void import('./settings/SettingsPreview').then(({SettingsPreview})=>createRoot(document.getElementById('root')!).render(<StrictMode><SettingsPreview/></StrictMode>));
} else if(preview) {
 void import('./arrange/GroupPreview').then(({GroupPreview})=>createRoot(document.getElementById('root')!).render(<StrictMode><GroupPreview/></StrictMode>));
} else {
 (window as any).__TAURI_INTERNALS__?.invoke?.('frontend_error', { message: 'main.tsx loaded, view=' + (new URLSearchParams(location.search).get('view') ?? 'main') });
 const mount = () => {
   const root = document.getElementById('root');
   if (!root || (root as any)._mounted) return;
   (root as any)._mounted = true;
   (window as any).__TAURI_INTERNALS__?.invoke?.('frontend_error', { message: 'main.tsx mounting React App' });
   const preferences = agent.get().localPreferences;
   if (preferences) setLanguage(preferences.ui_language);
   createRoot(root).render(<StrictMode><App /></StrictMode>);
 };
 const timer = setTimeout(mount, 300);
 void start(new URLSearchParams(location.search).get('view') ?? 'main')
   .then(() => {
     clearTimeout(timer);
     mount();
   })
   .catch((err) => {
     clearTimeout(timer);
     (window as any).__TAURI_INTERNALS__?.invoke?.('frontend_error', { message: 'start error: ' + String(err) });
     mount();
   });
}
