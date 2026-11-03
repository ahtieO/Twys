/* TWYS 2.9: user-selected appearance only. Analytics and prices are unchanged. */
(() => {
  'use strict';
  const root=document.documentElement;
  const button=document.getElementById('theme-switch');
  if(!button)return;
  const current=()=>root.dataset.theme==='light'?'light':'dark';
  const update=()=>{
    const isLight=current()==='light';
    button.textContent=isLight?'☾ Dark':'☀ Light';
    button.setAttribute('aria-label',isLight?'Switch to dark mode':'Switch to light mode');
    button.setAttribute('aria-pressed',String(isLight));
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content',isLight?'#f4f6f8':'#0a0d11');
  };
  button.addEventListener('click',async()=>{
    const selected=current()==='dark'?'light':'dark';
    root.dataset.theme=selected;
    try{localStorage.setItem('twys_theme',selected)}catch(_){}
    update();
    // TradingView widgets use colorTheme at construction; reload active page.
    if(typeof navigate==='function'&&typeof state!=='undefined')
      await navigate(state.page||'marketdesk');
  });
  update();
})();
