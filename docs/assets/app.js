(() => {
  const root = document.documentElement;
  const TABS = ['how', 'rating', 'run', 'improve'];
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const LEAVE = { duration: still ? 0 : 130, easing: 'ease-in', fill: 'forwards' };
  const ENTER = { duration: still ? 0 : 220, easing: 'cubic-bezier(.2,.7,.2,1)' };
  const HIDDEN = { opacity: 0, transform: 'translateY(5px)' };
  const SHOWN = { opacity: 1, transform: 'none' };

  const panel = (tab) => document.getElementById(`panel-${tab}`);
  const ladder = document.getElementById('ladder');
  const glow = document.querySelector('.glow');

  async function swap(leaving, change) {
    await leaving.animate([SHOWN, HIDDEN], LEAVE).finished;
    const entering = change() || leaving;
    leaving.getAnimations().forEach((animation) => animation.cancel());
    await entering.animate([HIDDEN, SHOWN], ENTER).finished;
  }

  function route() {
    const [tab, target = ''] = decodeURIComponent(location.hash.slice(1)).split('/');
    return { tab: TABS.includes(tab) ? tab : 'how', target };
  }

  function remember(target) {
    history.replaceState(null, '', `#${root.dataset.tab}${target ? `/${target}` : ''}`);
  }

  function markTab(smooth) {
    document.querySelectorAll('.tab').forEach((tab) => {
      if (tab.dataset.tab !== root.dataset.tab) return tab.removeAttribute('aria-current');
      tab.setAttribute('aria-current', 'page');
      tab.parentElement.scrollTo({ left: tab.offsetLeft - 16, behavior: smooth && !still ? 'smooth' : 'auto' });
    });
  }

  function setOpen(item, open, instant) {
    if (instant) item.classList.add('is-instant');
    item.classList.toggle('is-open', open);
    item.querySelector(':scope > [data-fold]').setAttribute('aria-expanded', open);
    if (instant) {
      void item.offsetHeight;
      requestAnimationFrame(() => item.classList.remove('is-instant'));
    }
  }

  function reveal(tab, target, smooth) {
    const item = tab === 'rating' && target && document.getElementById(`card-${target}`);
    if (!item) return;
    setOpen(item, true);
    const top = item.getBoundingClientRect().top + scrollY - document.querySelector('.top').offsetHeight - 16;
    scrollTo({ top, behavior: smooth && !still ? 'smooth' : 'auto' });
  }

  function switchTab(tab, prepare) {
    if (tab === root.dataset.tab) {
      prepare();
      return Promise.resolve();
    }
    return swap(panel(root.dataset.tab), () => {
      root.dataset.tab = tab;
      root.dispatchEvent(new CustomEvent('tabchange'));
      markTab(true);
      scrollTo(0, 0);
      prepare();
      return panel(tab);
    });
  }

  async function show({ tab, target }) {
    if (tab === root.dataset.tab) {
      reveal(tab, target, true);
      return;
    }
    await switchTab(tab, () => reveal(tab, target, false));
  }

  function selectStage(key, instant) {
    const current = document.querySelector('[data-stage-panel]:not([hidden])');
    const next = document.querySelector(`[data-stage-panel="${key}"]`);
    if (!next || current === next) return Promise.resolve();
    document.querySelectorAll('[data-stage]').forEach((node) => {
      node.setAttribute('aria-pressed', node.dataset.stage === key);
    });
    const change = () => {
      if (current) current.hidden = true;
      next.hidden = false;
      return next;
    };
    if (instant || !current) {
      change();
      return Promise.resolve();
    }
    return swap(current, change);
  }

  function reorder(direction) {
    const sign = direction === 'asc' ? 1 : -1;
    swap(ladder, () => {
      [...ladder.children]
        .sort((a, b) => sign * (a.dataset.score - b.dataset.score))
        .forEach((card) => ladder.append(card));
      document.querySelectorAll('[data-order]').forEach((button) => {
        button.setAttribute('aria-pressed', button.dataset.order === direction);
      });
    });
  }

  let glowQueued = false;
  function fadeGlow() {
    glowQueued = false;
    const depth = Math.min(1, scrollY / (innerHeight * 0.6));
    glow.style.opacity = (1 - 0.8 * depth).toFixed(3);
  }

  document.addEventListener('click', (event) => {
    const fold = event.target.closest('[data-fold]');
    const order = event.target.closest('[data-order]');
    const stage = event.target.closest('[data-stage]');
    if (fold) {
      const item = fold.closest('.foldable');
      const open = !item.classList.contains('is-open');
      setOpen(item, open);
      if (item.dataset.slug) remember(open ? item.dataset.slug : '');
    } else if (order && order.getAttribute('aria-pressed') !== 'true') {
      reorder(order.dataset.order);
    } else if (stage) {
      selectStage(stage.dataset.stage, false);
    }
  });

  addEventListener('hashchange', () => show(route()));
  addEventListener(
    'scroll',
    () => {
      if (glowQueued) return;
      glowQueued = true;
      requestAnimationFrame(fadeGlow);
    },
    { passive: true },
  );

  window.Stand = {
    switchTab,
    setOpen,
    stage: selectStage,
    remember: (hash) => history.replaceState(null, '', `#${hash}`),
  };

  markTab(false);
  fadeGlow();
  reveal(route().tab, route().target, false);
})();
