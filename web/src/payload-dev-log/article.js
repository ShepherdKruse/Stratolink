
import { mountCharts } from './charts.js';

export function mountArticle(root = document) {
const controller = new AbortController();
const { signal } = controller;
mountCharts(root, signal);

const dialog = root.querySelector('.lightbox');
const image = dialog.querySelector('.lightbox-image');
const caption = dialog.querySelector('.lightbox-caption');
let origin;
root.addEventListener('click', event => {
  const link=event.target.closest('a[data-lightbox]');
  if (link && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) {
    event.preventDefault();
    origin=link;
    image.src=link.href;
    image.alt=link.querySelector('img')?.alt || '';
    caption.textContent=link.closest('figure')?.querySelector('figcaption')?.textContent || '';
    dialog.showModal();
  }
  const ref=event.target.closest('a[href^="#ref-"]');
  if (ref) root.querySelector('.references').open=true;
},{signal});
dialog.querySelector('button').addEventListener('click',()=>dialog.close());
dialog.addEventListener('click',event=>{
  if(event.target!==dialog)return;
  const b=dialog.getBoundingClientRect();
  if(event.clientX<b.left || event.clientX>b.right || event.clientY<b.top || event.clientY>b.bottom)dialog.close();
});
dialog.addEventListener('close',()=>origin?.focus({preventScroll:true}));

const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const videoObserver = new IntersectionObserver(entries => entries.forEach(({target,isIntersecting})=>{
  target.dataset.visible=String(isIntersecting);
  if(isIntersecting && !reducedMotion.matches && !document.hidden && target.dataset.userPaused!=='true') target.play().catch(()=>{});
  else {target.dataset.autoPause='true';target.pause();}
}),{threshold:.35});
root.querySelectorAll('video[data-autoplay]').forEach(video=>{
  if(reducedMotion.matches)video.autoplay=false;
  videoObserver.observe(video);
  video.addEventListener('click',()=>video.paused?video.play().catch(()=>{}):video.pause());
  video.addEventListener('keydown',event=>{if(event.key===' '||event.key==='Enter'){event.preventDefault();video.paused?video.play().catch(()=>{}):video.pause();}});
  video.addEventListener('pause',()=>{if(video.dataset.autoPause==='true')delete video.dataset.autoPause;else video.dataset.userPaused='true';});
  video.addEventListener('play',()=>{delete video.dataset.userPaused;delete video.dataset.autoPause;});
});
document.addEventListener('visibilitychange',()=>root.querySelectorAll('video[data-autoplay]').forEach(video=>{
 if(document.hidden){video.dataset.autoPause='true';video.pause();}
 else if(video.dataset.visible==='true'&&!reducedMotion.matches&&video.dataset.userPaused!=='true')video.play().catch(()=>{});
}),{signal});
reducedMotion.addEventListener('change',()=>{if(reducedMotion.matches)root.querySelectorAll('video[data-autoplay]').forEach(v=>{v.dataset.autoPause='true';v.pause();});},{signal});

return () => {
  controller.abort();
  videoObserver.disconnect();
  root.querySelectorAll('video').forEach(video => video.pause());
  if (dialog.open) dialog.close();
};
}
