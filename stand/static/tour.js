(() => {
  const steps = JSON.parse(document.getElementById('tour-steps').textContent);
  const root = document.documentElement;
  const header = document.querySelector('.top');
  const dock = document.getElementById('dock');
  const spot = document.getElementById('spot');
  const coach = document.getElementById('coach');
  const coachTitle = coach.querySelector('.coach__title');
  const coachText = coach.querySelector('.coach__text');
  const coachArrow = coach.querySelector('.coach__arrow');
  const coachButton = coach.querySelector('[data-tour-act="show"]');
  const ring = dock.querySelector('.ring');
  const ringLabel = ring.querySelector('span');
  const dockText = dock.querySelector('.dock__text');
  const dockTitle = dock.querySelector('.dock__title');
  const dockCount = dock.querySelector('.dock__count');
  const backButton = dock.querySelector('[data-tour-act="back"]');
  const nextLabel = dock.querySelector('[data-tour-act="next"] .btn__label');
  const exitButton = dock.querySelector('[data-tour-act="exit"]');
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ordinary = steps.filter((step) => !step.final).length;
  const GAP = 14;
  const AWAY = {
    up: 'Нужный элемент выше. Прокрутите вверх или нажмите «Показать».',
    down: 'Нужный элемент ниже. Прокрутите вниз или нажмите «Показать».',
    away: 'Этот шаг на другой вкладке.',
  };

  let index = -1;
  let target = null;
  let mode = '';
  let token = 0;
  let signature = '';
  let looping = false;

  const wait = (ms) => new Promise((done) => setTimeout(done, still ? 0 : ms));
  const frame = () => new Promise((done) => requestAnimationFrame(done));
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

  function band() {
    return {
      top: header.getBoundingClientRect().bottom + 12,
      bottom: dock.getBoundingClientRect().top - 12,
    };
  }

  function fitsBeside(rect) {
    if (innerWidth <= 900) return false;
    const width = coach.offsetWidth;
    return rect.right + GAP + width <= innerWidth - 12 || rect.left - GAP - width >= 12;
  }

  function plan(element) {
    const area = band();
    const room = area.bottom - area.top;
    const rect = element.getBoundingClientRect();
    const tall = coach.offsetHeight;
    let top;
    if (fitsBeside(rect)) top = rect.height <= room ? area.top + (room - rect.height) / 2 : area.top + 8;
    else if (rect.height + GAP + tall + 16 <= room) top = area.top + (room - rect.height - GAP - tall) / 2;
    else top = area.top + tall + GAP + 12;
    const limit = document.documentElement.scrollHeight - innerHeight;
    return clamp(scrollY + rect.top - top, 0, limit);
  }

  async function glide(y) {
    if (Math.abs(scrollY - y) < 2) return;
    scrollTo({ top: y, behavior: still ? 'auto' : 'smooth' });
    const started = performance.now();
    let previous = -1;
    let calm = 0;
    while (performance.now() - started < 1200) {
      await frame();
      if (Math.abs(scrollY - y) < 2) return;
      calm = scrollY === previous ? calm + 1 : 0;
      previous = scrollY;
      if (calm > 5) return;
    }
  }

  function prepare(step, instant) {
    let opened = false;
    step.open.forEach((id) => {
      const item = document.getElementById(id);
      if (item && !item.classList.contains('is-open')) {
        Stand.setOpen(item, true, instant);
        opened = true;
      }
    });
    const node = step.stage && document.getElementById(`stage-${step.stage}`);
    if (node && node.getAttribute('aria-pressed') !== 'true') {
      Stand.stage(step.stage, instant);
      opened = true;
    }
    return opened;
  }

  function writeCoach(text, withButton) {
    coachText.textContent = text;
    coachButton.hidden = !withButton;
  }

  function renderDock(step) {
    const number = step.final ? ordinary : index + 1;
    ring.style.setProperty('--p', Math.round((number / ordinary) * 100));
    backButton.disabled = index === 0;
    exitButton.style.visibility = step.final ? 'hidden' : '';
    nextLabel.textContent = step.final ? 'Завершить' : 'Дальше';
    const write = () => {
      ringLabel.textContent = step.final ? '✓' : String(number);
      dockTitle.textContent = step.title;
      dockCount.textContent = step.final ? 'Демонстрация пройдена' : `Шаг ${number} из ${ordinary}`;
    };
    if (!dockTitle.textContent || still) return write();
    dockText.animate([{ opacity: 1 }, { opacity: 0, transform: 'translateY(4px)' }], { duration: 120, easing: 'ease-in' })
      .finished.then(() => {
        write();
        dockText.animate([{ opacity: 0, transform: 'translateY(-4px)' }, { opacity: 1, transform: 'none' }], {
          duration: 220,
          easing: 'cubic-bezier(.2,.7,.2,1)',
        });
      });
  }

  function conceal() {
    spot.classList.remove('is-on');
    coach.classList.remove('is-on');
    mode = '';
  }

  function setMode(next) {
    if (mode === next) return;
    mode = next;
    const step = steps[index];
    writeCoach(next === 'on' ? step.text : AWAY[next], next !== 'on');
  }

  function aim(x, y, side, pointX, pointY) {
    const width = coach.offsetWidth;
    const height = coach.offsetHeight;
    coach.style.transform = `translate3d(${Math.round(x)}px, ${Math.round(y)}px, 0)`;
    coach.dataset.side = side;
    if (side === 'l' || side === 'r') {
      coachArrow.style.top = `${clamp(pointY - y - 7, 16, height - 30)}px`;
      coachArrow.style.left = '';
    } else {
      coachArrow.style.left = `${clamp(pointX - x - 7, 18, width - 32)}px`;
      coachArrow.style.top = '';
    }
    coach.classList.add('is-on');
  }

  function highlight(rect, area) {
    const pad = 8;
    const left = Math.max(rect.left - pad, 6);
    const right = Math.min(rect.right + pad, innerWidth - 6);
    const top = Math.max(rect.top - pad, area.top - 6);
    const bottom = Math.min(rect.bottom + pad, area.bottom + 6);
    spot.style.width = `${right - left}px`;
    spot.style.height = `${bottom - top}px`;
    spot.style.transform = `translate3d(${Math.round(left)}px, ${Math.round(top)}px, 0)`;
    spot.classList.add('is-on');

    const width = coach.offsetWidth;
    const height = coach.offsetHeight;
    const middleX = (left + right) / 2;
    const middleY = (top + bottom) / 2;
    const wide = innerWidth > 900;
    let side;
    let x;
    let y;
    if (wide && right + GAP + width <= innerWidth - 12) [side, x, y] = ['r', right + GAP, middleY - height / 2];
    else if (wide && left - GAP - width >= 12) [side, x, y] = ['l', left - GAP - width, middleY - height / 2];
    else if (bottom + GAP + height <= area.bottom) [side, x, y] = ['b', middleX - width / 2, bottom + GAP];
    else if (top - GAP - height >= area.top) [side, x, y] = ['t', middleX - width / 2, top - GAP - height];
    else [side, x, y] = ['in', middleX - width / 2, area.bottom - height];
    aim(clamp(x, 12, innerWidth - width - 12), clamp(y, area.top, area.bottom - height), side, middleX, middleY);
  }

  function park(where, area) {
    spot.classList.remove('is-on');
    const width = coach.offsetWidth;
    const height = coach.offsetHeight;
    const x = (innerWidth - width) / 2;
    const y = where === 'up' ? area.top + 8 : area.bottom - height - 8;
    aim(x, y, where === 'up' ? 'b' : where === 'down' ? 't' : 'in', innerWidth / 2, 0);
  }

  function place(force) {
    if (!target) return;
    const area = band();
    const rect = target.getBoundingClientRect();
    let next = 'on';
    if (!target.isConnected || !target.getClientRects().length) next = 'away';
    else {
      const top = Math.max(rect.top, area.top);
      const bottom = Math.min(rect.bottom, area.bottom);
      if (bottom - top < Math.min(28, rect.height / 2)) {
        next = rect.top + rect.height / 2 < (area.top + area.bottom) / 2 ? 'up' : 'down';
      }
    }
    const now = [next, rect.left, rect.top, rect.width, rect.height, innerWidth, innerHeight]
      .map((value) => (typeof value === 'number' ? Math.round(value) : value))
      .join('|');
    if (!force && now === signature) return;
    signature = now;
    setMode(next);
    if (next === 'on') highlight(rect, area);
    else park(next, area);
  }

  function loop() {
    if (index < 0) {
      looping = false;
      return;
    }
    place(false);
    requestAnimationFrame(loop);
  }

  async function go(position) {
    const step = steps[position];
    if (!step) return;
    const mine = ++token;
    index = position;
    root.dataset.tour = 'on';
    root.dataset.tourStep = String(position + 1);
    target = null;
    conceal();
    renderDock(step);
    coachTitle.textContent = step.title;
    writeCoach(step.text, false);
    mode = 'on';
    const element = () => document.getElementById(step.target);

    if (step.tab !== root.dataset.tab) {
      await Stand.switchTab(step.tab, () => {
        prepare(step, true);
        const found = element();
        if (found) scrollTo(0, plan(found));
      });
    } else {
      await wait(150);
      if (mine !== token) return;
      if (prepare(step, false)) await wait(400);
      if (mine !== token) return;
      const found = element();
      if (found) await glide(plan(found));
    }
    if (mine !== token) return;
    Stand.remember(step.hash);
    target = element() || header;
    signature = '';
    place(true);
    if (!looping) {
      looping = true;
      requestAnimationFrame(loop);
    }
  }

  function start() {
    go(0);
  }

  function stop() {
    token += 1;
    index = -1;
    target = null;
    conceal();
    root.dataset.tour = 'off';
    delete root.dataset.tourStep;
  }

  function next() {
    if (index < 0) return;
    if (steps[index].final) stop();
    else go(index + 1);
  }

  function back() {
    if (index > 0) go(index - 1);
  }

  function show() {
    if (mode === 'away' || !target) go(index);
    else glide(plan(target));
  }

  const actions = { start, next, back, exit: stop, show };
  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-tour-act]');
    if (button && !button.disabled) actions[button.dataset.tourAct]();
  });

  addEventListener('keydown', (event) => {
    if (index < 0 || event.altKey || event.metaKey || event.ctrlKey || event.shiftKey) return;
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      next();
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      back();
    } else if (event.key === 'Escape') {
      stop();
    }
  });

  addEventListener('resize', () => place(true));
  root.dataset.tour = 'off';
})();
