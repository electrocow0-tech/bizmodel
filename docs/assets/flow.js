(() => {
  const flow = document.getElementById('flow');
  if (!flow) return;
  const root = document.documentElement;
  const canvas = flow.querySelector('.flow__canvas');
  const context = canvas.getContext('2d');
  const nodes = [...flow.querySelectorAll('.flow__node')];
  const lanes = [...flow.querySelectorAll('.flow__lane')];
  const numbers = JSON.parse(flow.dataset.flow);
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const SPAWN_PER_SECOND = 14;
  const CROSSING_SECONDS = 9;
  const COLORS = {
    live: [214, 228, 255],
    rejected: [255, 122, 112],
    queued: [134, 134, 139],
    unsure: [243, 189, 102],
    done: [111, 214, 162],
  };

  const share = (part, whole) => (whole ? part / whole : 0);
  const exits = [
    { at: 2, kinds: [['rejected', share(numbers.sourced - numbers.filtered, numbers.sourced)], ['queued', share(numbers.filtered - numbers.deep, numbers.sourced)]] },
    { at: 3, kinds: [['unsure', share(numbers.deep - numbers.passed, numbers.deep)]] },
    { at: 5, kinds: [['rejected', share(numbers.passed - numbers.carded, numbers.passed)]] },
  ];

  const sprites = Object.fromEntries(Object.entries(COLORS).map(([name, rgb]) => [name, sprite(rgb)]));
  let ratio = 1;
  let anchors = [];
  let lengths = [];
  let total = 0;
  let vertical = false;
  let track = null;
  let dots = [];
  let running = false;
  let last = 0;
  let debt = 0;
  let onScreen = true;

  function sprite([r, g, b]) {
    const size = 48;
    const image = document.createElement('canvas');
    image.width = image.height = size;
    const paint = image.getContext('2d');
    const glow = paint.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    glow.addColorStop(0, `rgba(${r},${g},${b},1)`);
    glow.addColorStop(0.18, `rgba(${r},${g},${b},0.85)`);
    glow.addColorStop(0.45, `rgba(${r},${g},${b},0.18)`);
    glow.addColorStop(1, `rgba(${r},${g},${b},0)`);
    paint.fillStyle = glow;
    paint.fillRect(0, 0, size, size);
    return image;
  }

  function measure() {
    const box = flow.getBoundingClientRect();
    if (!box.width) return false;
    ratio = Math.min(2, devicePixelRatio || 1);
    canvas.width = Math.round(box.width * ratio);
    canvas.height = Math.round(box.height * ratio);
    const centers = nodes.map((node, index) => {
      const r = node.getBoundingClientRect();
      const lane = lanes[index].getBoundingClientRect();
      return { x: r.left - box.left + r.width / 2, y: r.top - box.top + r.height / 2, left: r.left - box.left, lane: lane.top - box.top + lane.height / 2 };
    });
    vertical = centers.length > 1 && Math.abs(centers[1].y - centers[0].y) > Math.abs(centers[1].x - centers[0].x);
    anchors = vertical ? centers.map((c) => ({ x: c.left - 24, y: c.y })) : centers.map((c) => ({ x: c.x, y: c.lane }));
    if (anchors.length > 1) {
      const first = anchors[0];
      const end = anchors[anchors.length - 1];
      const dx = (anchors[1].x - first.x) / 2;
      const dy = (anchors[1].y - first.y) / 2;
      anchors = [{ x: first.x - dx, y: first.y - dy }, ...anchors, { x: end.x + dx * 0.6, y: end.y + dy * 0.6 }];
    }
    lengths = anchors.slice(1).map((a, i) => Math.hypot(a.x - anchors[i].x, a.y - anchors[i].y));
    total = lengths.reduce((sum, length) => sum + length, 0);
    track = drawTrack(box);
    return true;
  }

  function drawTrack(box) {
    const layer = document.createElement('canvas');
    layer.width = canvas.width;
    layer.height = canvas.height;
    const paint = layer.getContext('2d');
    paint.scale(ratio, ratio);
    const first = anchors[0];
    const end = anchors[anchors.length - 1];
    const gradient = paint.createLinearGradient(first.x, first.y, end.x, end.y);
    gradient.addColorStop(0, 'rgba(120,160,255,0.55)');
    gradient.addColorStop(0.5, 'rgba(150,120,255,0.45)');
    gradient.addColorStop(1, 'rgba(90,210,190,0.5)');
    paint.lineCap = 'round';
    paint.lineJoin = 'round';
    paint.strokeStyle = gradient;
    for (const [width, alpha, blur] of [[10, 0.18, 18], [2, 0.9, 0]]) {
      paint.globalAlpha = alpha;
      paint.lineWidth = width;
      paint.shadowColor = 'rgba(140,170,255,0.8)';
      paint.shadowBlur = blur;
      paint.beginPath();
      anchors.forEach((point, index) => (index ? paint.lineTo(point.x, point.y) : paint.moveTo(point.x, point.y)));
      paint.stroke();
    }
    return layer;
  }

  function pointAt(distance) {
    let left = distance;
    for (let index = 0; index < lengths.length; index += 1) {
      if (left <= lengths[index]) {
        const a = anchors[index];
        const b = anchors[index + 1];
        const t = lengths[index] ? left / lengths[index] : 0;
        return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
      }
      left -= lengths[index];
    }
    return anchors[anchors.length - 1];
  }

  function distanceTo(index) {
    return lengths.slice(0, index).reduce((sum, length) => sum + length, 0);
  }

  function fate() {
    for (const exit of exits) {
      let roll = Math.random();
      for (const [kind, chance] of exit.kinds) {
        if (roll < chance) return { stop: distanceTo(exit.at), kind };
        roll -= chance;
      }
    }
    return { stop: total, kind: 'done' };
  }

  function spawn(offset = 0) {
    const depth = Math.random();
    dots.push({
      travelled: offset,
      speed: (total / CROSSING_SECONDS) * (0.8 + depth * 0.4),
      lane: (Math.random() - 0.5) * (vertical ? 12 : 14),
      size: 5 + depth * 7,
      alpha: 0.45 + depth * 0.55,
      leaving: 0,
      ...fate(),
    });
  }

  function step(seconds) {
    debt += seconds * SPAWN_PER_SECOND;
    while (debt >= 1) {
      spawn();
      debt -= 1;
    }
    for (const dot of dots) {
      if (dot.leaving) dot.leaving += seconds;
      else {
        dot.travelled = Math.min(dot.stop, dot.travelled + dot.speed * seconds);
        if (dot.travelled >= dot.stop) dot.leaving = 0.0001;
      }
    }
    dots = dots.filter((dot) => dot.leaving < 1);
  }

  function draw() {
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(track, 0, 0);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    for (const dot of dots) {
      const point = pointAt(dot.travelled);
      let x = point.x + (vertical ? dot.lane : 0);
      let y = point.y + (vertical ? 0 : dot.lane);
      let alpha = dot.alpha;
      let size = dot.size;
      let color = 'live';
      if (dot.leaving) {
        const t = dot.leaving;
        color = dot.kind;
        alpha *= 1 - t;
        if (dot.kind === 'done') size *= 1 + t * 1.5;
        else if (vertical) x -= 26 * t * t + 6 * t;
        else y += 30 * t * t + 6 * t;
      }
      context.globalAlpha = alpha;
      context.drawImage(sprites[color], x - size, y - size, size * 2, size * 2);
    }
    context.globalAlpha = 1;
  }

  function settle() {
    dots = [];
    for (let i = 0; i < 90; i += 1) {
      const dot = (spawn(Math.random() * total), dots[dots.length - 1]);
      if (dot.travelled >= dot.stop) dot.leaving = 0.3 + Math.random() * 0.5;
    }
  }

  function frame(now) {
    if (!running) return;
    const seconds = Math.min(0.05, (now - last) / 1000 || 0);
    last = now;
    step(seconds);
    draw();
    requestAnimationFrame(frame);
  }

  function visible() {
    return root.dataset.tab === 'how' && !document.hidden && onScreen;
  }

  function update() {
    const should = visible();
    if (should && !running) {
      if (!measure()) return;
      if (still) {
        settle();
        draw();
        return;
      }
      if (!dots.length) {
        for (let i = 0; i < 60; i += 1) step(1 / SPAWN_PER_SECOND);
      }
      running = true;
      last = performance.now();
      requestAnimationFrame(frame);
    } else if (!should) {
      running = false;
    }
  }

  new ResizeObserver(() => {
    if (!visible()) return;
    measure();
    if (!running) draw();
  }).observe(flow);
  new IntersectionObserver(([entry]) => {
    onScreen = entry.isIntersecting;
    update();
  }).observe(flow);
  root.addEventListener('tabchange', update);
  document.addEventListener('visibilitychange', update);
  update();
})();
