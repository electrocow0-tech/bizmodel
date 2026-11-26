(() => {
  const root = document.documentElement;
  const TABS = ['rating', 'compare', 'forest', 'agents', 'documents'];
  const ANCHORS = { rating: 'card', forest: 'gate', agents: 'iso' };
  const PICK_LIMIT = 3;
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const LEAVE = { duration: still ? 0 : 130, easing: 'ease-in', fill: 'forwards' };
  const ENTER = { duration: still ? 0 : 220, easing: 'cubic-bezier(.2,.7,.2,1)' };
  const HIDDEN = { opacity: 0, transform: 'translateY(5px)' };
  const SHOWN = { opacity: 1, transform: 'none' };

  const panel = (tab) => document.getElementById(`panel-${tab}`);
  const ladder = document.getElementById('ladder');
  const grid = document.getElementById('cmp');
  const picks = [...document.querySelectorAll('[data-pick]')];
  const pickCount = document.getElementById('pick-count');
  const glow = document.querySelector('.glow');

  async function swap(leaving, change) {
    await leaving.animate([SHOWN, HIDDEN], LEAVE).finished;
    const entering = change() || leaving;
    leaving.getAnimations().forEach((animation) => animation.cancel());
    await entering.animate([HIDDEN, SHOWN], ENTER).finished;
  }

  function route() {
    const [tab, target = ''] = decodeURIComponent(location.hash.slice(1)).split('/');
    return { tab: TABS.includes(tab) ? tab : 'rating', target };
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
    if (tab === 'compare') {
      if (target) choose(target.split(',').slice(0, PICK_LIMIT));
      return;
    }
    const item = target && document.getElementById(`${ANCHORS[tab]}-${target}`);
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

  function chosen() {
    return picks.filter((pick) => pick.getAttribute('aria-pressed') === 'true').map((pick) => pick.dataset.pick);
  }

  function choose(slugs) {
    const full = slugs.length >= PICK_LIMIT;
    picks.forEach((pick) => {
      const on = slugs.includes(pick.dataset.pick);
      pick.setAttribute('aria-pressed', on);
      pick.setAttribute('aria-disabled', !on && full);
    });
    grid.querySelectorAll('[data-col]').forEach((column) => {
      column.hidden = !slugs.includes(column.dataset.col);
    });
    pickCount.textContent = full
      ? `Выбрано ${PICK_LIMIT} из ${PICK_LIMIT}. Чтобы взять другую модель, снимите одну.`
      : `Выбрано ${slugs.length} из ${PICK_LIMIT}`;
  }

  function togglePick(slug) {
    const now = chosen();
    if (!now.includes(slug) && now.length >= PICK_LIMIT) return;
    const next = now.includes(slug) ? now.filter((other) => other !== slug) : [...now, slug];
    swap(grid, () => choose(next));
    remember(next.join(','));
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
    const pick = event.target.closest('[data-pick]');
    if (fold) {
      const item = fold.closest('.foldable');
      const open = !item.classList.contains('is-open');
      setOpen(item, open);
      if (item.dataset.slug) remember(open ? item.dataset.slug : '');
    } else if (order && order.getAttribute('aria-pressed') !== 'true') {
      reorder(order.dataset.order);
    } else if (pick) {
      togglePick(pick.dataset.pick);
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
    choose: (slugs) => grid && choose(slugs),
    remember: (hash) => history.replaceState(null, '', `#${hash}`),
  };

  markTab(false);
  fadeGlow();
  if (grid) choose(chosen());
  reveal(route().tab, route().target, false);
})();
