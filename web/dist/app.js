const $ = (id) => document.getElementById(id);
const phases = ['Spooling', 'Ascending', 'Hovering', 'Descending', 'Landed'];
let endpoint = localStorage.getItem('ingenuity-relay') || '';
let lease = null, online = false, paused = false, replayTime = 0, lastClock = performance.now();
let recording, history = [], lastSeq = -1, lastCamera = 0, controlsBusy = false;
let gustTimer = null, gustDeadline = 0, gustRemaining = 0, polling = false;
$('endpoint').value = endpoint;
const canvas = $('flight'), context = canvas.getContext('2d');

async function request(path, body) {
  const response = await fetch(endpoint + path, {
    method: body ? 'POST' : 'GET',
    headers: body ? {'Content-Type': 'application/json'} : {},
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(1800), cache: 'no-store',
  });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || `HTTP ${response.status}`);
  return value;
}

function knob(key, value) {
  const input = $(key), block = input.closest('.knob');
  input.value = value;
  block.querySelector('output').textContent = Number(value).toFixed(key === 'wind' ? 1 : 2);
  const angle = -135 + 270 * (value - Number(input.min)) / (Number(input.max) - Number(input.min));
  block.querySelector('.dial').style.setProperty('--rotation', `${angle}deg`);
}
for (const key of ['wind', 'stiffness', 'damping']) {
  $(key).addEventListener('input', () => knob(key, Number($(key).value)));
  $(key).addEventListener('change', () => send({[key]: Number($(key).value)}));
  knob(key, Number($(key).value));
}

async function send(values) {
  if (!online || !lease || controlsBusy) return;
  controlsBusy = true;
  try {
    await request('/api/controls', {lease, values});
    $('control-note').textContent = 'Setting sent. Watch the applied values and the flight response.';
  } catch (error) {
    $('control-note').textContent = error.message;
  } finally { controlsBusy = false; }
}

$('claim').onclick = async () => {
  try {
    if (lease) {
      await request('/api/release', {lease});
      lease = null;
    } else { lease = (await request('/api/lease', {})).lease; }
    permissions();
  } catch (error) { $('control-note').textContent = error.message; }
};
function permissions() {
  $('claim').disabled = !online;
  $('claim').textContent = lease ? 'Release control' : 'Take control';
  $('knobs').disabled = !online || !lease;
  $('control-note').textContent = online
    ? lease ? 'Control active. Changes apply to this flight.' : 'Take control to adjust the flight settings.'
    : 'Recorded flight. Controls require a live bench.';
  document.querySelector('.replay-controls').hidden = online;
}
$('reset').onclick = () => {
  clearTimeout(gustTimer); gustDeadline = 0;
  for (const [key, value] of Object.entries({wind: 0, stiffness: 1, damping: 1})) knob(key, value);
  send({wind: 0, stiffness: 1, damping: 1});
};
$('gust').onclick = async () => {
  if (!lease || !online) return;
  try {
    await request('/api/gust', {lease}); knob('wind', 60);
    gustRemaining = 8;
  } catch (error) { $('control-note').textContent = error.message; }
};
$('connection').onsubmit = (event) => {
  event.preventDefault();
  let value = $('endpoint').value.trim().replace(/\/$/, '');
  try {
    if (value && !['http:', 'https:'].includes(new URL(value).protocol)) throw new Error('Use an HTTP or HTTPS relay URL.');
    if (location.protocol === 'https:' && value.startsWith('http:')) throw new Error('An HTTPS page needs an HTTPS relay.');
    if (lease) request('/api/release', {lease}).catch(() => {});
    endpoint = value; lease = null; online = false;
    localStorage.setItem('ingenuity-relay', value); permissions(); poll();
  } catch (error) { $('control-note').textContent = error.message; }
};
$('play').onclick = () => { paused = !paused; $('play').textContent = paused ? 'Play replay' : 'Pause replay'; };
$('seek').oninput = () => { replayTime = Number($('seek').value); };

function bars(commands = [0, 0, 0, 0]) {
  ['Collective', 'Roll', 'Pitch', 'Yaw'].forEach((name, i) => {
    const row = document.querySelector(`[data-command="${i}"]`);
    row.querySelector('output').textContent = commands[i].toFixed(3);
    row.querySelector('i').style.width = `${Math.min(1, Math.abs(commands[i])) * 100}%`;
  });
}
['Collective', 'Roll', 'Pitch', 'Yaw'].forEach((name, i) => {
  const row = document.createElement('div'); row.className = 'bar'; row.dataset.command = i;
  row.innerHTML = `<label>${name}<output>0.000</output></label><div class="bar-track"><i></i></div>`;
  $('command-bars').append(row);
});

function draw(sample, samples) {
  const width = canvas.clientWidth, height = canvas.clientHeight, ratio = devicePixelRatio || 1;
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = width * ratio; canvas.height = height * ratio;
  }
  context.setTransform(ratio, 0, 0, ratio, 0, 0); context.clearRect(0, 0, width, height);
  const left = 48, top = 22, right = width - 22, bottom = height - 35;
  const x = (t) => left + t / 154 * (right - left), y = (z) => bottom - z / 24 * (bottom - top);
  context.font = '12px system-ui'; context.lineWidth = 1;
  for (let z = 0; z <= 20; z += 5) {
    context.strokeStyle = '#283642'; context.beginPath(); context.moveTo(left, y(z)); context.lineTo(right, y(z)); context.stroke();
    context.fillStyle = '#a2b0bc'; context.fillText(`${z} m`, 9, y(z) + 4);
  }
  for (let t = 0; t <= 150; t += 30) context.fillText(`${t}s`, x(t) - 8, height - 10);
  function line(points, color, accessor) {
    context.beginPath(); context.strokeStyle = color; context.lineWidth = 2;
    let first = true;
    for (const point of points) {
      const value = accessor(point);
      if (value === null || value === undefined) { first = true; continue; }
      if (first) context.moveTo(x(point.time_s), y(value)); else context.lineTo(x(point.time_s), y(value));
      first = false;
    }
    context.stroke();
  }
  line(recording.reference, '#5ce6fa70', (p) => p.z_m);
  line(recording.reference.filter((p) => p.time_s <= sample.time_s), '#5ce6fa', (p) => p.z_m);
  line(samples, '#ffb55b', (p) => p.z_m);
  context.beginPath(); context.fillStyle = '#ffb55b'; context.arc(x(sample.time_s), y(sample.z_m), 4, 0, 2 * Math.PI); context.fill();
}
function show(sample, samples) {
  $('altitude').textContent = sample.z_m.toFixed(2);
  $('gap').textContent = sample.reference_error_m === null ? '—' : sample.reference_error_m.toFixed(3);
  $('collective').textContent = sample.collective.toFixed(3);
  $('phase').textContent = phases[sample.phase] || 'Unknown';
  $('time').textContent = `${sample.time_s.toFixed(2)} s`;
  $('sequence').textContent = `${sample.sequence ?? Math.round(sample.time_s * 100)} packets`;
  $('rtt').textContent = online && sample.rtt_ms !== undefined ? `${sample.rtt_ms.toFixed(1)} ms round trip` : 'RECORDED FLIGHT';
  $('applied').textContent = `Applied: wind ${(sample.wind_mps || 0).toFixed(1)} m/s · altitude gain ${(sample.stiffness || 1).toFixed(2)}× · damping ${(sample.damping || 1).toFixed(2)}×`;
  bars(sample.commands || [sample.collective, 0, 0, 0]); draw(sample, samples);
}

async function poll() {
  if (polling || !recording) return;
  polling = true;
  try {
    const data = await request('/api/state');
    gustRemaining = data.gust_remaining_s || 0;
    if (gustRemaining === 0 && gustDeadline > 0) knob('wind', data.controls.wind);
    gustDeadline = gustRemaining;
    const wasOnline = online; online = Boolean(data.online && data.sample);
    if (online !== wasOnline) { history = []; lastSeq = -1; permissions(); }
    if (online) {
      if (lease && !data.occupied) { lease = null; permissions(); }
      $('mode').textContent = data.sample.hardware === 'raspberry' ? 'LIVE · RASPBERRY PI' : 'LIVE · LOCAL CONTROLLER';
      $('mode').className = 'badge live';
      if (data.sample.sequence < lastSeq) history = [];
      if (data.sample.sequence !== lastSeq) {
        history.push(data.sample); if (history.length > 2000) history.shift(); lastSeq = data.sample.sequence;
        document.querySelector('.signal-path').classList.toggle('pulse');
      }
      if (!lease) for (const [key, value] of Object.entries(data.controls)) knob(key, value);
      show(data.sample, history);
      $('events').replaceChildren(...data.events.slice(-5).reverse().map((event) => {
        const li = document.createElement('li'); li.textContent = event.text; return li;
      }));
      if (data.camera && performance.now() - lastCamera > 600) {
        lastCamera = performance.now(); $('camera').src = `${endpoint}/api/camera?t=${Date.now()}`;
        $('camera-kind').textContent = 'LIVE · SIMULATED';
      }
    }
  } catch {
    if (online) { online = false; permissions(); }
  } finally { polling = false; }
}
setInterval(poll, 300);
setInterval(async () => {
  if (!lease || !online) return;
  try { await request('/api/lease', {lease}); } catch { lease = null; permissions(); }
}, 8000);

function animate(now) {
  const dt = Math.min((now - lastClock) / 1000, 0.2); lastClock = now;
  if (recording && !online) {
    if (!paused) replayTime = (replayTime + dt) % recording.duration_s;
    const index = Math.min(recording.samples.length - 1, Math.floor(replayTime / recording.interval_s));
    show(recording.samples[index], recording.samples.slice(0, index + 1));
    $('mode').textContent = 'REPLAY · BENCH OFFLINE'; $('mode').className = 'badge';
    $('seek').value = replayTime; $('seek-label').textContent = `${replayTime.toFixed(1)} s`;
    if ($('camera-kind').textContent !== 'RECORDED STILL') { $('camera').src = 'navcam.png'; $('camera-kind').textContent = 'RECORDED STILL'; }
  }
  $('gust').textContent = online && gustRemaining > 0 ? `Gust · ${gustRemaining.toFixed(1)} s sim` : '60 m/s gust · 8 s sim';
  requestAnimationFrame(animate);
}
permissions();
fetch('replay.json').then((r) => { if (!r.ok) throw new Error('Recording unavailable'); return r.json(); }).then((value) => {
  recording = value; $('seek').max = value.duration_s; requestAnimationFrame(animate); poll();
}).catch(() => { $('mode').textContent = 'RECORDING UNAVAILABLE'; $('control-note').textContent = 'The recording could not be loaded. Reload the page.'; });
