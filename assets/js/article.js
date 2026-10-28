// Mark the section being read in the contents list.
const tocLinks = [...document.querySelectorAll('.toc a')];
const linkFor = new Map(tocLinks.map(a => [a.getAttribute('href').slice(1), a]));
const watcher = new IntersectionObserver(entries => {
  for (const entry of entries) {
    if (!entry.isIntersecting) continue;
    tocLinks.forEach(a => a.classList.remove('active'));
    const link = linkFor.get(entry.target.id);
    if (link) link.classList.add('active');
  }
}, { rootMargin: '-80px 0px -70% 0px' });
document.querySelectorAll('main section[id]').forEach(section => watcher.observe(section));

// Open linked figures over the page. A click on the dark area around the figure, the close button or
// Escape closes it; a click with a modifier key still opens the image on its own.
const viewer = document.createElement('div');
viewer.className = 'viewer';
viewer.hidden = true;
viewer.setAttribute('role', 'dialog');
viewer.setAttribute('aria-modal', 'true');
viewer.setAttribute('aria-label', 'Full figure');
viewer.innerHTML = '<button class="viewer-close" type="button" aria-label="Close">&times;</button><img alt="">';
document.body.append(viewer);
const viewerImg = viewer.querySelector('img');
let opener = null;

function closeViewer() {
  viewer.hidden = true;
  viewerImg.removeAttribute('src');
  document.body.classList.remove('viewing');
  if (opener) opener.focus();
}

viewer.addEventListener('click', event => { if (event.target !== viewerImg) closeViewer(); });
document.addEventListener('keydown', event => { if (event.key === 'Escape' && !viewer.hidden) closeViewer(); });
for (const link of document.querySelectorAll('main a[href$=".jpg"], main a[href$=".png"]')) {
  link.addEventListener('click', event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    opener = link;
    viewerImg.src = link.getAttribute('href');
    const shown = link.closest('figure') && link.closest('figure').querySelector('img');
    viewerImg.alt = shown ? shown.alt : 'Full figure';
    viewer.hidden = false;
    document.body.classList.add('viewing');
    viewer.querySelector('.viewer-close').focus();
  });
}

// Copy the BibTeX entry; if the browser refuses, jump to it instead.
for (const button of document.querySelectorAll('[data-copy]')) {
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(document.getElementById(button.dataset.copy).textContent);
      button.textContent = 'Copied';
      setTimeout(() => { button.textContent = button.dataset.label; }, 1500);
    } catch (err) {
      location.hash = '#bibtex';
    }
  });
}
