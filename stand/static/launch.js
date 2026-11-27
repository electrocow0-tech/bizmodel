(() => {
  const form = document.getElementById('launch');
  if (!form) return;
  const data = JSON.parse(document.getElementById('launch-data').textContent);
  const mock = new URLSearchParams(location.search).has('mock');
  const staticHost = location.protocol === 'file:' || location.hostname.endsWith('github.io');
  const api = mock ? mockApi() : liveApi();
  const POLL_RUNNING_MS = 3000;
  const POLL_IDLE_MS = 30000;
  const FINISHED_KEY = 'bizmodel-demo-finished';

  const go = document.getElementById('launch-go');
  const note = document.getElementById('launch-note');
  const estimate = document.getElementById('estimate');
  const estimateDetail = document.getElementById('estimate-detail');
  const progressBar = document.getElementById('progress-bar');
  const progressText = document.getElementById('progress-text');
  const weights = [...form.querySelectorAll('[data-weight]')];
  const ranges = [...form.querySelectorAll('input[type="range"]')];
  const providerNames = Object.fromEntries(
    [...document.querySelectorAll('#budgets [data-provider]')].map((row) => [row.dataset.provider, row.firstElementChild.textContent]),
  );

  let status = { available: false, running: false };
  let message = '';
  let pollTimer = 0;
  let estimateTimer = 0;
  let sawRunning = false;

  const money = (value) => `$${value.toFixed(2).replace('.', ',')}`;
  const plural = (n, one, few, many) => {
    const tail = n % 100;
    if (n % 10 === 1 && tail !== 11) return one;
    if ([2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(tail)) return few;
    return many;
  };

  function params() {
    const value = (name) => form.elements[name].value;
    return {
      sample_size: Number(value('sample_size')),
      deep_check: Number(value('deep_check')),
      industries: [...form.querySelectorAll('[name="industries"]:checked')].map((box) => box.value),
      weights: Object.fromEntries(weights.map((input) => [input.dataset.weight, Number(input.value)])),
      assumptions: {
        team: value('team').trim(),
        test_budget_usd: Number(value('test_budget_usd')),
        horizon_weeks: Number(value('horizon_weeks')),
      },
      profile: form.querySelector('[name="profile"]:checked')?.value || data.defaults.profile,
      max_usd: Number(value('max_usd')),
    };
  }

  function paint(input) {
    const low = Number(input.min);
    const high = Number(input.max);
    input.style.setProperty('--fill', `${((Number(input.value) - low) / (high - low)) * 100}%`);
    document.getElementById(input.dataset.output).textContent = input.value;
  }

  function rebalance(changed) {
    const others = weights.filter((input) => input !== changed);
    const rest = 100 - Number(changed.value);
    const current = others.map((input) => Number(input.value));
    const sum = current.reduce((a, b) => a + b, 0);
    const exact = current.map((value) => (sum ? (value * rest) / sum : rest / others.length));
    const whole = exact.map(Math.floor);
    let left = rest - whole.reduce((a, b) => a + b, 0);
    exact
      .map((value, index) => [value - whole[index], index])
      .sort((a, b) => b[0] - a[0])
      .forEach(([, index]) => {
        if (left > 0) {
          whole[index] += 1;
          left -= 1;
        }
      });
    others.forEach((input, index) => {
      input.value = whole[index];
      paint(input);
    });
  }

  function localEstimate(p) {
    const factor = p.profile === 'dev' ? 0.2 : 1;
    const usd = {};
    for (const [provider, part] of Object.entries(data.costs)) {
      const cost = part.prescreen * (p.sample_size / data.measured.sample) + part.deep * (p.deep_check / data.measured.deep);
      usd[provider] = Math.round(cost * factor * 100) / 100;
    }
    return { usd, minutes: Math.max(2, Math.round(2 + p.sample_size / 100 + p.deep_check * 0.4)) };
  }

  function showEstimate(result) {
    const parts = Object.entries(result.usd);
    const sum = parts.reduce((total, [, value]) => total + value, 0);
    estimate.textContent = `около ${money(sum)}`;
    const split = parts.map(([provider, value]) => `${providerNames[provider] || provider} ${money(value)}`).join(', ');
    estimateDetail.textContent = `${split}. Около ${result.minutes} ${plural(result.minutes, 'минуты', 'минут', 'минут')}.`;
  }

  function refreshEstimate() {
    clearTimeout(estimateTimer);
    estimateTimer = setTimeout(async () => {
      const p = params();
      try {
        showEstimate(status.available ? await api.estimate(p) : localEstimate(p));
      } catch {
        showEstimate(localEstimate(p));
      }
    }, 300);
  }

  function say(text, link) {
    note.textContent = text;
    if (link && /^https?:\/\//.test(link)) {
      const anchor = document.createElement('a');
      anchor.href = link;
      anchor.textContent = link.replace(/^https?:\/\//, '');
      note.append(' ', anchor);
    }
  }

  function render() {
    const running = Boolean(status.running);
    form.classList.toggle('is-running', running);
    go.disabled = !status.available || running || !form.elements.code.value.trim();
    if (!status.available) say('Запуск работает на живом стенде', data.liveUrl);
    else if (running) say('Прогон идёт. Стенд обновится сам, когда он закончится.');
    else say(message || status.error || (mock ? 'Демо-режим: подойдёт код demo, прогон займёт 20 секунд.' : ''));

    const progress = status.progress;
    const done = progress && progress.total ? progress.done / progress.total : 0;
    progressBar.style.setProperty('--v', running ? Math.max(0.03, done).toFixed(3) : '0');
    progressText.textContent = running && progress ? progress.message : 'Прогон не идёт.';

    for (const row of document.querySelectorAll('#budgets [data-provider]')) {
      const budget = status.budget && status.budget[row.dataset.provider];
      if (!budget) continue;
      row.querySelector('.budgets__value').textContent = `потрачено ${money(budget.spent)} из ${money(budget.limit)}`;
      row.querySelector('.meter-line i').style.setProperty('--v', Math.min(1, budget.spent / budget.limit).toFixed(3));
    }
  }

  function reloadSmoothly() {
    document.body.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 300, fill: 'forwards' }).finished.then(() => location.reload());
  }

  async function poll() {
    clearTimeout(pollTimer);
    try {
      status = await api.status();
    } catch {
      status = { available: false, running: false };
    }
    if (status.running) sawRunning = true;
    else if (sawRunning && status.last_run && status.last_run !== data.runId) return reloadSmoothly();
    render();
    if (status.available) pollTimer = setTimeout(poll, status.running ? POLL_RUNNING_MS : POLL_IDLE_MS);
  }

  function problem(reply) {
    const body = reply.body || {};
    if (body.error) return body.error;
    if (reply.code === 422) {
      const field = Array.isArray(body.detail) && body.detail[0] && body.detail[0].loc ? body.detail[0].loc.slice(-1)[0] : '';
      return `Проверьте параметры${field ? `: поле ${field}` : ''}.`;
    }
    return 'Сервер не принял запуск. Попробуйте ещё раз позже.';
  }

  form.addEventListener('input', (event) => {
    const input = event.target;
    if (input.dataset.weight) rebalance(input);
    if (input.type === 'range') paint(input);
    message = '';
    if (input.name !== 'code') refreshEstimate();
    render();
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const p = params();
    if (!p.industries.length) {
      message = 'Выберите хотя бы одну отрасль.';
      return render();
    }
    go.disabled = true;
    let reply;
    try {
      reply = await api.start(form.elements.code.value.trim(), p);
    } catch {
      reply = { ok: false, code: 0, body: { error: 'Сервер не ответил. Попробуйте ещё раз позже.' } };
    }
    message = reply.ok ? '' : problem(reply);
    if (reply.ok) {
      status = { ...status, running: true, progress: null };
      sawRunning = true;
    }
    render();
    if (reply.ok) pollTimer = setTimeout(poll, POLL_RUNNING_MS);
  });

  function liveApi() {
    async function call(path, options = {}) {
      if (staticHost) throw new Error('static');
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 6000);
      try {
        const response = await fetch(`/api/${path}`, {
          ...options,
          cache: 'no-store',
          signal: controller.signal,
          headers: { 'Content-Type': 'application/json' },
        });
        const body = await response.json().catch(() => ({}));
        return { ok: response.ok, code: response.status, body };
      } finally {
        clearTimeout(timer);
      }
    }
    return {
      async status() {
        const reply = await call('status');
        if (!reply.ok || typeof reply.body.available !== 'boolean') throw new Error('unavailable');
        return reply.body;
      },
      async estimate(p) {
        const reply = await call('estimate', { method: 'POST', body: JSON.stringify(p) });
        if (!reply.ok) throw new Error('estimate');
        return reply.body;
      },
      start: (code, p) => call('runs', { method: 'POST', body: JSON.stringify({ code, params: p }) }),
    };
  }

  function mockApi() {
    const RUN_MS = 20000;
    const STAGES = [
      ['prescreen', 0.2, 'Дешёвый фильтр', (p) => p.sample_size],
      ['gate', 0.62, 'Проверка по критериям', (p) => p.deep_check],
      ['card', 0.82, 'Карточки', (p) => Math.min(p.deep_check, 9)],
      ['advice', 0.94, 'Советник', (p) => Math.min(p.deep_check, 9)],
      ['stand', 1, 'Сборка стенда', () => 1],
    ];
    const spent = Object.fromEntries(
      Object.entries(data.costs).map(([provider, part]) => [provider, part.prescreen + part.deep]),
    );
    let started = 0;
    let planned = null;
    let lastRun = data.runId;

    const budget = () =>
      Object.fromEntries(Object.entries(data.budgets).map(([provider, limit]) => [provider, { limit, spent: spent[provider] || 0 }]));

    function progressAt(share) {
      let from = 0;
      for (const [stage, until, title, count] of STAGES) {
        if (share < until) {
          const totalCount = count(planned);
          const done = Math.floor(((share - from) / (until - from)) * totalCount);
          return { stage, done, total: totalCount, message: `${title}: ${done} из ${totalCount}` };
        }
        from = until;
      }
      return { stage: 'stand', done: 1, total: 1, message: 'Сборка стенда: 1 из 1' };
    }

    return {
      async status() {
        if (started) {
          const share = (Date.now() - started) / RUN_MS;
          if (share < 1) return { available: true, running: true, progress: progressAt(share), budget: budget(), last_run: lastRun, error: null };
          started = 0;
          lastRun = `${data.runId}-demo`;
          for (const [provider, value] of Object.entries(localEstimate(planned).usd)) spent[provider] = (spent[provider] || 0) + value;
          sessionStorage.setItem(FINISHED_KEY, lastRun);
        }
        return { available: true, running: false, progress: null, budget: budget(), last_run: lastRun, error: null };
      },
      async estimate(p) {
        return localEstimate(p);
      },
      async start(code, p) {
        if (code !== 'demo') return { ok: false, code: 403, body: { error: 'Неверный код запуска.' } };
        if (started) return { ok: false, code: 409, body: { error: 'Прогон уже идёт.' } };
        const cost = Object.values(localEstimate(p).usd).reduce((a, b) => a + b, 0);
        if (cost > p.max_usd) {
          return { ok: false, code: 402, body: { error: `Оценка ${money(cost)} выше потолка ${money(p.max_usd)}. Поднимите потолок или уменьшите выборку.` } };
        }
        started = Date.now();
        planned = p;
        return { ok: true, code: 202, body: { started: true } };
      },
    };
  }

  ranges.forEach(paint);
  showEstimate(localEstimate(params()));
  if (mock && sessionStorage.getItem(FINISHED_KEY)) {
    sessionStorage.removeItem(FINISHED_KEY);
    message = 'Демо-прогон завершён. На живом стенде здесь уже были бы новые карточки.';
  }
  render();
  poll().then(refreshEstimate);
})();
