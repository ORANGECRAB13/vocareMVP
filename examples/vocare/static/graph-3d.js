const graphEl = document.querySelector('#graph');
const statusText = document.querySelector('#statusText');
const nodeCount = document.querySelector('#nodeCount');
const linkCount = document.querySelector('#linkCount');
const selectionDetails = document.querySelector('#selectionDetails');
const legendEl = document.querySelector('#legend');
const accessPathEl = document.querySelector('#accessPath');
const limitInput = document.querySelector('#limitInput');
const searchInput = document.querySelector('#searchInput');
const refreshButton = document.querySelector('#refreshButton');
const traceButton = document.querySelector('#traceButton');
const callButton = document.querySelector('#callButton');
const talkButton = document.querySelector('#talkButton');
const hangupButton = document.querySelector('#hangupButton');
const callStatus = document.querySelector('#callStatus');
const callTranscript = document.querySelector('#callTranscript');

const palette = ['#60a5fa', '#34d399', '#f59e0b', '#f87171', '#a78bfa', '#2dd4bf', '#f472b6', '#c084fc', '#38bdf8', '#facc15'];
const svgNS = 'http://www.w3.org/2000/svg';
const viewBox = { x: -640, y: -380, width: 1280, height: 760 };

const tracePath = [
  'customer:jack',
  'identity:biometric',
  'identity:biometric:confidence',
  'identity:biometric:timestamp',
  'identity:kyc',
  'identity:passport',
  'contact:mobile',
  'contact:mobile:push-channel',
  'contact:email',
  'device:iphone',
  'device:iphone:trust-score',
  'address:registered',
  'profile:premier',
  'card:visa4481',
  'card:visa4481:status',
  'txn:electronics',
  'txn:electronics:merchant',
  'risk:freeze',
  'risk:freeze:reason',
  'risk:fraud-case',
  'account:offset',
  'loan:home',
  'payment:home-loan',
  'payment:home-loan:record-impact',
  'case:incident',
  'consent:grace',
  'remediation:grace',
  'remediation:grace:expiry',
  'consent:digital-card',
  'card:digital',
  'card:digital:wallets',
  'fulfilment:physical-card'
];

const traceCopy = {
  'customer:jack': ['Call context opened', 'Jack is the stable customer anchor before account data is discussed.'],
  'identity:biometric': ['Verification approved', 'The app push confirms Jack before Aria accesses sensitive information.'],
  'identity:biometric:confidence': ['Confidence checked', 'The biometric confidence score clears the security threshold.'],
  'identity:biometric:timestamp': ['Approval timing checked', 'The timestamp confirms this approval belongs to the current call.'],
  'identity:kyc': ['Identity profile checked', 'KYC status confirms a low-risk verified customer record.'],
  'identity:passport': ['Document match', 'Stored identity documents support the verified customer context.'],
  'contact:mobile': ['Trusted contact point', 'The verified mobile number links the push approval back to Jack.'],
  'contact:mobile:push-channel': ['Push channel confirmed', 'The graph confirms app push is the preferred verification path.'],
  'contact:email': ['Digital preference read', 'Statement and digital communication preferences are visible.'],
  'device:iphone': ['Trusted device', 'The approval came from a known CommBank app device.'],
  'device:iphone:trust-score': ['Device trust score', 'The known device has a strong trust score.'],
  'address:registered': ['Registered address guardrail', 'Card fulfilment must use this address only.'],
  'profile:premier': ['Premier relationship', 'Aria uses the relationship profile to keep the call calm and concise.'],
  'card:visa4481': ['Visa card freeze', 'The affected card is retrieved after Jack confirms the topic.'],
  'card:visa4481:status': ['Freeze status read', 'The card status confirms the Visa is temporarily frozen.'],
  'txn:electronics': ['Purchase trigger', 'The transaction that caused the freeze is surfaced for confirmation.'],
  'txn:electronics:merchant': ['Merchant detail read', 'Aria checks merchant, category, and amount before asking Jack.'],
  'risk:freeze': ['Risk signal', 'The freeze decision explains why the card was temporarily restricted.'],
  'risk:freeze:reason': ['Freeze reason read', 'The model reason explains why automated controls fired.'],
  'risk:fraud-case': ['Review state', 'Fraud review is present but not escalated while Jack can confirm.'],
  'account:offset': ['Linked offset account', 'Aria follows the graph to the account affected by the freeze.'],
  'loan:home': ['Home loan context', 'The offset account is tied to Jack\'s home loan repayment.'],
  'payment:home-loan': ['Rejected payment impact', 'The rejected payment is surfaced only after Jack confirms the purchase.'],
  'payment:home-loan:record-impact': ['Record impact checked', 'The payment can still be protected inside the grace window.'],
  'case:incident': ['Premier care case', 'The case pulls card, payment, consent, and remediation together.'],
  'consent:grace': ['Grace consent required', 'Aria must ask before applying the grace period.'],
  'remediation:grace': ['Grace period applied', 'Once Jack agrees, the grace period prevents record impact.'],
  'remediation:grace:expiry': ['Grace expiry calculated', 'The expiry node gives Aria the exact confirmation date.'],
  'consent:digital-card': ['Digital card consent', 'Aria asks before activating a replacement digital card.'],
  'card:digital': ['Digital card active', 'The replacement digital card can be used immediately.'],
  'card:digital:wallets': ['Wallet compatibility checked', 'Apple Pay and Google Pay support is confirmed.'],
  'fulfilment:physical-card': ['Physical card shipment', 'The physical card is express-shipped to the registered address only.']
};

let fullGraphData = { nodes: [], links: [] };
let graphData = { nodes: [], links: [] };
let colorByLabel = new Map();
let nodeById = new Map();
let visibleNodeIds = new Set();
let exploredNodeIds = new Set();
let activeTraceNodeId = 'customer:jack';
let traceTimer = 0;
let starTimer = 0;
let traceIndex = 0;
let callState = 'idle';
let peerConnection = null;
let dataChannel = null;
let localStream = null;
let localTrack = null;
let remoteAudio = null;
let activePcId = null;
let graphPollTimer = 0;
let pingTimer = 0;
const transcriptSeen = new Set();

initialize();

async function initialize() {
  refreshButton.addEventListener('click', loadGraph);
  traceButton.addEventListener('click', toggleTrace);
  callButton.addEventListener('click', connectCall);
  hangupButton.addEventListener('click', disconnectCall);
  talkButton.addEventListener('mousedown', startTalking);
  talkButton.addEventListener('mouseup', stopTalking);
  talkButton.addEventListener('mouseleave', stopTalking);
  talkButton.addEventListener('touchstart', startTalking);
  talkButton.addEventListener('touchend', stopTalking);
  searchInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      focusSearchResult();
    }
  });
  window.addEventListener('pagehide', () => disconnectCall(true));
  await loadGraph();
}

async function loadGraph() {
  const limit = Math.max(100, Math.min(10000, Number(limitInput.value || 2500)));
  statusText.textContent = 'Loading...';
  refreshButton.disabled = true;

  try {
    const response = await fetch(`/api/graph/visualization?limit=${encodeURIComponent(limit)}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    fullGraphData = normalizePayload(await response.json());
    statusText.textContent = 'Context loaded - waiting for call';
  } catch (_) {
    fullGraphData = mockGraphData();
    statusText.textContent = 'Mock context loaded - waiting for call';
  } finally {
    apply2DLayout(fullGraphData);
    colorByLabel = buildColorMap(fullGraphData.nodes);
    nodeById = new Map(fullGraphData.nodes.map((node) => [node.id, node]));
    activeTraceNodeId = 'customer:jack';
    visibleNodeIds = new Set(['customer:jack']);
    exploredNodeIds = new Set(['customer:jack']);
    updateVisibleGraph();
    renderLegend();
    showNodeDetails(nodeById.get('customer:jack') || fullGraphData.nodes[0]);
    renderAccessPath(activeTraceNodeId);
    nodeCount.textContent = formatNumber(fullGraphData.nodes.length);
    linkCount.textContent = formatNumber(fullGraphData.links.length);
    refreshButton.disabled = false;
  }
}

function normalizePayload(payload) {
  return {
    nodes: (payload.nodes || []).map((node) => ({
      ...node,
      label: node.label || node.id,
      labels: node.labels || [node.primaryLabel || 'Node'],
      primaryLabel: node.primaryLabel || node.labels?.[0] || 'Node',
      properties: node.properties || {}
    })),
    links: (payload.links || []).map((link) => ({ ...link, properties: link.properties || {} }))
  };
}

function beginStarExpansion() {
  clearTimers();
  statusText.textContent = 'Context graph expanding from Jack';
  activeTraceNodeId = 'customer:jack';
  visibleNodeIds = new Set(['customer:jack']);
  exploredNodeIds = new Set(['customer:jack']);
  updateVisibleGraph();

  const order = expansionOrder();
  let index = 0;
  starTimer = setInterval(() => {
    const batch = index < 8 ? 2 : 3;
    for (let i = 0; i < batch && index < order.length; i += 1) {
      visibleNodeIds.add(order[index]);
      index += 1;
    }
    updateVisibleGraph(true);
    if (index >= order.length) {
      clearInterval(starTimer);
      starTimer = 0;
      statusText.textContent = `Loaded ${formatNumber(fullGraphData.links.length)} relationships`;
    }
  }, 105);
}

function toggleTrace() {
  if (traceTimer) {
    clearInterval(traceTimer);
    traceTimer = 0;
    traceButton.classList.remove('is-running');
    return;
  }
  beginStarExpansion();
  traceButton.classList.add('is-running');
  traceIndex = 0;
  traceTimer = setInterval(() => {
    const id = tracePath[traceIndex];
    const node = nodeById.get(id);
    if (node) focusNode(node, true);
    traceIndex += 1;
    if (traceIndex >= tracePath.length) {
      clearInterval(traceTimer);
      traceTimer = 0;
      traceButton.classList.remove('is-running');
    }
  }, 520);
}

function clearTimers() {
  if (starTimer) clearInterval(starTimer);
  if (traceTimer) clearInterval(traceTimer);
  starTimer = 0;
  traceTimer = 0;
  traceButton.classList.remove('is-running');
}

function expansionOrder() {
  const ids = new Set(fullGraphData.nodes.map((node) => node.id));
  const traced = tracePath.filter((id) => ids.has(id) && id !== 'customer:jack');
  const rest = fullGraphData.nodes.map((node) => node.id).filter((id) => id !== 'customer:jack' && !traced.includes(id));
  return [...traced, ...rest];
}

function updateVisibleGraph(animateNew = false) {
  const visibleLinks = fullGraphData.links.filter((link) => visibleNodeIds.has(nodeId(link.source)) && visibleNodeIds.has(nodeId(link.target)));
  graphData = {
    nodes: fullGraphData.nodes.filter((node) => visibleNodeIds.has(node.id)),
    links: visibleLinks
  };
  renderGraph(animateNew);
  renderAccessPath(activeTraceNodeId);
}

function renderGraph(animateNew = false) {
  graphEl.innerHTML = '';
  const svg = svgEl('svg', { class: 'context-svg', viewBox: `${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`, role: 'img' });
  const defs = svgEl('defs');
  defs.appendChild(svgEl('filter', { id: 'softGlow', x: '-40%', y: '-40%', width: '180%', height: '180%' }, [
    svgEl('feGaussianBlur', { stdDeviation: '4', result: 'blur' }),
    svgEl('feMerge', {}, [svgEl('feMergeNode', { in: 'blur' }), svgEl('feMergeNode', { in: 'SourceGraphic' })])
  ]));
  svg.appendChild(defs);

  svg.appendChild(svgEl('text', { class: 'graph-title', x: -604, y: -338 }, ['CONTEXT GRAPH']));
  svg.appendChild(svgEl('text', { class: 'graph-subtitle', x: -604, y: -316 }, [statusText.textContent]));

  const linkLayer = svgEl('g', { class: 'links' });
  for (const link of graphData.links) linkLayer.appendChild(renderLink(link));
  svg.appendChild(linkLayer);

  const nodeLayer = svgEl('g', { class: 'nodes' });
  for (const node of graphData.nodes) nodeLayer.appendChild(renderNode(node, animateNew));
  svg.appendChild(nodeLayer);

  graphEl.appendChild(svg);
}

function renderLink(link) {
  const source = nodeById.get(nodeId(link.source));
  const target = nodeById.get(nodeId(link.target));
  const active = isActiveTraceLink(link);
  const trace = isTraceLink(link);
  const dim = exploredNodeIds.size > 1 && !active && !trace ? ' dim' : '';
  const color = colorForLabel(target?.primaryLabel || source?.primaryLabel);
  const mid = midpoint(source, target);
  const group = svgEl('g', { class: `graph-link${trace ? ' trace' : ''}${active ? ' active' : ''}${dim}`, style: `--link-color:${color}` });
  group.appendChild(svgEl('path', { d: curvePath(source, target) }));
  if (active || trace) {
    group.appendChild(svgEl('text', { class: 'link-label', x: mid.x, y: mid.y - 6 }, [link.type]));
  }
  group.addEventListener('click', () => showLinkDetails(link));
  return group;
}

function renderNode(node, animateNew) {
  const active = node.id === activeTraceNodeId;
  const center = node.id === 'customer:jack';
  const dim = exploredNodeIds.size > 1 && !exploredNodeIds.has(node.id) && !linkedToActive(node.id) ? ' dim' : '';
  const entering = animateNew && !exploredNodeIds.has(node.id) ? ' entering' : '';
  const color = colorForLabel(node.primaryLabel);
  const radius = nodeRadius(node);
  const group = svgEl('g', {
    class: `graph-node${active ? ' active' : ''}${center ? ' center' : ''}${dim}${entering}`,
    transform: `translate(${node.x} ${node.y})`,
    style: `--node-color:${color}`
  });
  group.appendChild(svgEl('circle', { class: 'node-halo', r: radius + 12 }));
  group.appendChild(svgEl('circle', { class: 'node-orb', r: radius }));
  group.appendChild(svgEl('circle', { class: 'node-core', r: Math.max(3, radius * 0.32) }));
  group.appendChild(svgEl('text', { class: 'node-label', y: radius + 18 }, [node.label]));
  group.appendChild(svgEl('text', { class: 'node-meta', y: radius + 32 }, [nodeMeta(node)]));
  group.addEventListener('click', () => focusNode(node, true));
  return group;
}

function focusNode(node, fromUser = false) {
  if (!node) return;
  revealNodeAndContext(node.id);
  activeTraceNodeId = node.id;
  exploredNodeIds.add(node.id);
  if (fromUser) {
    const traceIndexForNode = tracePath.indexOf(node.id);
    if (traceIndexForNode >= 0) {
      tracePath.slice(0, traceIndexForNode + 1).forEach((id) => exploredNodeIds.add(id));
    }
  }
  updateVisibleGraph();
  showNodeDetails(node);
}

function revealNodeAndContext(id) {
  visibleNodeIds.add(id);
  const traceIndexForNode = tracePath.indexOf(id);
  if (traceIndexForNode >= 0) {
    tracePath.slice(0, traceIndexForNode + 1).forEach((traceId) => visibleNodeIds.add(traceId));
  }
  for (const link of fullGraphData.links) {
    const source = nodeId(link.source);
    const target = nodeId(link.target);
    if (source === id || target === id || tracePath.includes(source) && tracePath.includes(target)) {
      visibleNodeIds.add(source);
      visibleNodeIds.add(target);
    }
  }
}

function focusSearchResult() {
  const query = normalize(searchInput.value);
  if (!query) return;
  const node = fullGraphData.nodes.find((candidate) =>
    normalize(candidate.label).includes(query) ||
    normalize(candidate.id).includes(query) ||
    normalize(candidate.primaryLabel).includes(query)
  );
  if (node) focusNode(node, true);
}

function focusEventNode(event) {
  const id = event.node_id || event.nodeId;
  const map = {
    identity: 'identity:biometric',
    card_freeze: 'card:visa4481',
    mortgage_payment: 'payment:home-loan',
    grace_period: 'remediation:grace',
    replacement_card: 'card:digital'
  };
  const target = nodeById.get(map[id] || id);
  if (target) focusNode(target, true);
}

async function connectCall() {
  if (callState === 'connecting' || callState === 'connected') return;
  setCallState('connecting', 'Requesting microphone...');
  clearTranscript();

  try {
    localStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    });
    localTrack = localStream.getAudioTracks()[0] || null;
    if (localTrack) localTrack.enabled = false;

    setCallState('connecting', 'Fetching relay path...');
    let iceServers = [{ urls: 'stun:stun.l.google.com:19302' }];
    try {
      const iceResponse = await fetch('/api/ice');
      if (iceResponse.ok) {
        const body = await iceResponse.json();
        if (body.iceServers?.length) iceServers = body.iceServers;
      }
    } catch (_) {}

    peerConnection = new RTCPeerConnection({ iceServers, iceTransportPolicy: 'relay' });
    localStream.getTracks().forEach((track) => peerConnection.addTrack(track, localStream));
    peerConnection.addTransceiver('audio', { direction: 'recvonly' });

    dataChannel = peerConnection.createDataChannel('data', { ordered: true });
    dataChannel.onopen = () => {
      pingTimer = window.setInterval(() => {
        if (dataChannel?.readyState === 'open') dataChannel.send('ping');
      }, 2000);
    };

    peerConnection.ontrack = (event) => {
      if (remoteAudio) {
        remoteAudio.pause();
        remoteAudio.srcObject = null;
      }
      remoteAudio = new Audio();
      remoteAudio.srcObject = event.streams[0];
      remoteAudio.autoplay = true;
    };

    peerConnection.onconnectionstatechange = () => {
      if (peerConnection?.connectionState === 'connected') {
        setCallState('connected', 'Aria is live. Hold to talk.');
        beginStarExpansion();
      }
      if (peerConnection?.connectionState === 'failed') {
        setCallState('error', 'Connection failed. Try again.');
        disconnectCall();
      }
    };

    setCallState('connecting', 'Negotiating voice pipeline...');
    await peerConnection.setLocalDescription(await peerConnection.createOffer());
    await waitForIce(peerConnection);

    const requestedPcId = `foundry-graph-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const response = await fetch('/api/offer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sdp: peerConnection.localDescription.sdp,
        type: peerConnection.localDescription.type,
        pc_id: requestedPcId,
        stt: 'elevenlabs',
        llm: 'mistral',
        tts: 'elevenlabs',
        mode: 'indiv'
      })
    });
    if (!response.ok) throw new Error(`Offer failed (${response.status})`);
    const answer = await response.json();
    activePcId = answer.pc_id || requestedPcId;
    await peerConnection.setRemoteDescription(answer);
    startGraphPolling(activePcId);
  } catch (error) {
    console.error('[AriaCall]', error);
    setCallState('error', error.message || 'Unable to connect call.');
    disconnectCall();
  }
}

function disconnectCall(keepalive = false) {
  stopTalking();
  if (graphPollTimer) clearInterval(graphPollTimer);
  if (pingTimer) clearInterval(pingTimer);
  graphPollTimer = 0;
  pingTimer = 0;
  if (dataChannel) {
    dataChannel.onopen = null;
    try { dataChannel.close(); } catch (_) {}
  }
  if (peerConnection) {
    peerConnection.ontrack = null;
    peerConnection.onconnectionstatechange = null;
    try { peerConnection.getSenders().forEach((sender) => sender.track && sender.track.stop()); } catch (_) {}
    try { peerConnection.close(); } catch (_) {}
  }
  if (localStream) {
    try { localStream.getTracks().forEach((track) => track.stop()); } catch (_) {}
  }
  if (remoteAudio) {
    try {
      remoteAudio.pause();
      remoteAudio.srcObject = null;
    } catch (_) {}
  }
  if (activePcId) notifyHangup(activePcId, keepalive);

  dataChannel = null;
  peerConnection = null;
  localStream = null;
  localTrack = null;
  remoteAudio = null;
  activePcId = null;
  if (callState !== 'error') setCallState('idle', 'Aria is ready.');
}

function startTalking(event) {
  if (event) event.preventDefault();
  if (callState !== 'connected' || !localTrack) return;
  localTrack.enabled = true;
  talkButton.classList.add('is-talking');
  talkButton.textContent = 'Listening...';
}

function stopTalking(event) {
  if (event) event.preventDefault();
  if (localTrack) localTrack.enabled = false;
  talkButton.classList.remove('is-talking');
  talkButton.textContent = 'Hold to talk';
}

function setCallState(nextState, message) {
  callState = nextState;
  callStatus.textContent = message;
  callButton.disabled = nextState === 'connecting' || nextState === 'connected';
  talkButton.disabled = nextState !== 'connected';
  hangupButton.disabled = nextState !== 'connecting' && nextState !== 'connected';
}

function waitForIce(pc) {
  return new Promise((resolve) => {
    if (pc.iceGatheringState === 'complete') return resolve();
    const check = () => {
      if (pc.iceGatheringState === 'complete') {
        pc.removeEventListener('icegatheringstatechange', check);
        resolve();
      }
    };
    pc.addEventListener('icegatheringstatechange', check);
    setTimeout(resolve, 1500);
  });
}

function notifyHangup(pcId, keepalive) {
  const body = JSON.stringify({ pc_id: pcId });
  if (keepalive && navigator.sendBeacon) {
    try {
      if (navigator.sendBeacon('/api/hangup', new Blob([body], { type: 'application/json' }))) return;
    } catch (_) {}
  }
  fetch('/api/hangup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive
  }).catch(() => {});
}

function startGraphPolling(pcId) {
  if (graphPollTimer) clearInterval(graphPollTimer);
  const poll = async () => {
    try {
      const response = await fetch(`/api/graph/poll?pc_id=${encodeURIComponent(pcId)}`);
      const body = await response.json();
      for (const event of body.events || []) {
        if (event.type === 'user_transcription') addTranscript('user', event.text);
        if (event.type === 'bot_transcription') addTranscript('agent', event.text);
        if (event.type === 'node_access') focusEventNode(event);
      }
      if (body.closed) disconnectCall();
    } catch (_) {}
  };
  poll();
  graphPollTimer = window.setInterval(poll, 350);
}

function addTranscript(role, text) {
  const cleanText = String(text || '').trim();
  if (!cleanText) return;
  const key = `${role}:${cleanText.toLowerCase()}`;
  if (transcriptSeen.has(key)) return;
  transcriptSeen.add(key);
  if (transcriptSeen.size > 80) transcriptSeen.delete(transcriptSeen.values().next().value);

  const line = document.createElement('div');
  line.className = `call-line ${role}`;
  line.textContent = `${role === 'user' ? 'Jack' : 'Aria'}: ${cleanText}`;
  callTranscript.appendChild(line);
  while (callTranscript.children.length > 8) callTranscript.removeChild(callTranscript.firstChild);
  callTranscript.scrollTop = callTranscript.scrollHeight;
}

function clearTranscript() {
  callTranscript.innerHTML = '';
  transcriptSeen.clear();
}

window.addTranscript = addTranscript;

function showNodeDetails(node) {
  if (!node) return;
  const note = traceCopy[node.id];
  const traceNote = note
    ? `<div class="trace-note"><strong>${escapeHtml(note[0])}</strong><span>${escapeHtml(note[1])}</span></div>`
    : '';
  selectionDetails.innerHTML = `
    <h3>${escapeHtml(node.label)}</h3>
    <p class="muted">${escapeHtml((node.labels || []).join(' / '))}</p>
    ${traceNote}
    ${propertyTable(node.properties)}
  `;
}

function showLinkDetails(link) {
  selectionDetails.innerHTML = `
    <h3>${escapeHtml(link.type)}</h3>
    <p class="muted">${escapeHtml(nodeLabel(link.source))} -> ${escapeHtml(nodeLabel(link.target))}</p>
    ${propertyTable(link.properties)}
  `;
}

function renderLegend() {
  legendEl.innerHTML = [...colorByLabel.entries()]
    .map(([label, color]) => `<div class="legend-item"><span class="swatch" style="background:${color}"></span>${escapeHtml(label)}</div>`)
    .join('');
}

function renderAccessPath(activeId) {
  accessPathEl.innerHTML = tracePath
    .filter((id) => nodeById.has(id))
    .map((id) => {
      const node = nodeById.get(id);
      const active = id === activeId ? ' active' : '';
      return `<div class="path-item${active}"><span class="swatch" style="background:${colorForLabel(node.primaryLabel)}"></span>${escapeHtml(node.label)}</div>`;
    })
    .join('');
}

function apply2DLayout(data) {
  const traceNodes = tracePath.map((id) => data.nodes.find((node) => node.id === id)).filter(Boolean);
  traceNodes.forEach((node, index) => {
    if (node.id === 'customer:jack') {
      node.x = 0;
      node.y = 0;
      return;
    }
    const angle = -Math.PI * 0.92 + (index / Math.max(1, traceNodes.length - 1)) * Math.PI * 1.84;
    const radius = 150 + Math.min(190, index * 10);
    node.x = Math.cos(angle) * radius;
    node.y = Math.sin(angle) * radius * 0.72;
  });

  const buckets = new Map();
  for (const node of data.nodes) {
    if (tracePath.includes(node.id)) continue;
    const parentId = parentFor(node.id, data.links);
    if (!buckets.has(parentId)) buckets.set(parentId, []);
    buckets.get(parentId).push(node);
  }

  for (const [parentId, nodes] of buckets.entries()) {
    const parent = data.nodes.find((node) => node.id === parentId) || data.nodes.find((node) => node.id === 'customer:jack') || { x: 0, y: 0 };
    nodes.forEach((node, index) => {
      const side = parent.x >= 0 ? 1 : -1;
      const angle = (index / Math.max(1, nodes.length)) * Math.PI * 1.25 - Math.PI * 0.62;
      const radius = 86 + index * 12;
      node.x = parent.x + side * Math.cos(angle) * radius;
      node.y = parent.y + Math.sin(angle) * radius * 0.72;
    });
  }
}

function parentFor(id, links) {
  const incoming = links.find((link) => nodeId(link.target) === id);
  if (incoming) return nodeId(incoming.source);
  const outgoing = links.find((link) => nodeId(link.source) === id);
  return outgoing ? nodeId(outgoing.target) : 'customer:jack';
}

function curvePath(source, target) {
  if (!source || !target) return '';
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const curve = Math.min(90, Math.max(-90, dx * 0.12));
  const cx = source.x + dx / 2 - dy * 0.08;
  const cy = source.y + dy / 2 + curve;
  return `M ${source.x} ${source.y} Q ${cx} ${cy} ${target.x} ${target.y}`;
}

function midpoint(source, target) {
  return {
    x: (source.x + target.x) / 2,
    y: (source.y + target.y) / 2
  };
}

function linkedToActive(id) {
  return fullGraphData.links.some((link) =>
    (nodeId(link.source) === activeTraceNodeId && nodeId(link.target) === id) ||
    (nodeId(link.target) === activeTraceNodeId && nodeId(link.source) === id)
  );
}

function isTraceLink(link) {
  const sourceIndex = tracePath.indexOf(nodeId(link.source));
  const targetIndex = tracePath.indexOf(nodeId(link.target));
  return sourceIndex >= 0 && targetIndex === sourceIndex + 1;
}

function isActiveTraceLink(link) {
  const targetIndex = tracePath.indexOf(activeTraceNodeId);
  return targetIndex > 0 && nodeId(link.source) === tracePath[targetIndex - 1] && nodeId(link.target) === activeTraceNodeId;
}

function nodeRadius(node) {
  if (node.id === 'customer:jack') return 24;
  if (node.id === activeTraceNodeId) return 19;
  if (tracePath.includes(node.id)) return 16;
  return 13;
}

function nodeMeta(node) {
  if (node.primaryLabel === 'Customer') return node.properties?.segment || 'Premier';
  if (node.primaryLabel === 'Evidence') return node.labels?.[1] || 'Evidence';
  return node.primaryLabel || 'Node';
}

function nodeLabel(value) {
  if (value && typeof value === 'object') return value.label || value.id;
  return nodeById.get(value)?.label || value;
}

function nodeId(value) {
  return value && typeof value === 'object' ? value.id : value;
}

function buildColorMap(nodes) {
  const labels = [...new Set(nodes.map((node) => node.primaryLabel || 'Node'))].sort();
  return new Map(labels.map((label, index) => [label, palette[index % palette.length]]));
}

function colorForLabel(label) {
  return colorByLabel.get(label || 'Node') || '#94a3b8';
}

function propertyTable(properties) {
  const rows = Object.entries(properties || {})
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `<tr><th>${escapeHtml(key)}</th><td>${escapeHtml(formatValue(value))}</td></tr>`)
    .join('');
  return rows ? `<table>${rows}</table>` : '<p class="muted">No properties.</p>';
}

function svgEl(tag, attrs = {}, children = []) {
  const element = document.createElementNS(svgNS, tag);
  for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
  for (const child of children) element.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
  return element;
}

function normalize(value) {
  return String(value || '').toLowerCase().trim();
}

function formatValue(value) {
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function formatNumber(value) {
  return new Intl.NumberFormat('en-US').format(value || 0);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function mockGraphData() {
  const nodes = [
    node('customer:jack', 'Jack Thompson', 'Customer', ['Customer', 'Premier'], { cif: 'CBA-PRM-882914', segment: 'Premier Banking', relationshipSince: '2016-04-18' }),
    node('identity:biometric', 'Biometric Push', 'Identity', ['Identity', 'SecurityControl'], { method: 'CommBank app biometric approval', status: 'Approved', confidence: '99.6%' }),
    node('identity:biometric:confidence', 'Biometric Confidence', 'Evidence', ['Evidence', 'VerificationDetail'], { score: '99.6%', threshold: '95%', decision: 'Pass' }),
    node('identity:biometric:timestamp', 'Approval Timestamp', 'Evidence', ['Evidence', 'VerificationDetail'], { approvedAt: 'Today 10:14:22 AEST', freshness: 'Current call' }),
    node('identity:kyc', 'KYC Profile', 'Identity', ['Identity', 'KYC'], { status: 'Current', riskTier: 'Low' }),
    node('identity:passport', 'Passport Record', 'Identity', ['Identity', 'Document'], { documentType: 'Passport', verification: 'Matched on file' }),
    node('contact:mobile', 'Mobile Number', 'Contact', ['Contact', 'PersonalInfo'], { mobile: '+61 4XX XXX 228', verified: 'Yes' }),
    node('contact:mobile:push-channel', 'Push Channel', 'Evidence', ['Evidence', 'ContactDetail'], { channel: 'CommBank app push', preferred: 'Yes' }),
    node('contact:email', 'Email', 'Contact', ['Contact', 'PersonalInfo'], { email: 'jack.thompson@example.com', statementDelivery: 'Digital' }),
    node('address:registered', 'Registered Address', 'Address', ['Address', 'PersonalInfo'], { address: 'Registered address on file', usage: 'Card fulfilment only' }),
    node('device:iphone', 'Trusted iPhone', 'Device', ['Device', 'Security'], { device: 'iPhone 15 Pro', trustScore: 'Strong' }),
    node('device:iphone:trust-score', 'Device Trust Score', 'Evidence', ['Evidence', 'DeviceDetail'], { trustScore: 'Strong', recentRisk: 'None' }),
    node('profile:premier', 'Premier Relationship', 'Preference', ['Preference', 'Relationship'], { rm: 'Aria', contactStyle: 'Short conversational steps' }),
    node('card:visa4481', 'Awards Visa 4481', 'Card', ['Card'], { product: 'CommBank Awards Visa', lastFour: '4481', status: 'Temporarily frozen' }),
    node('card:visa4481:status', 'Freeze Status', 'Evidence', ['Evidence', 'CardDetail'], { status: 'Temporarily frozen', reversible: 'Yes' }),
    node('txn:electronics', 'Electronics Purchase', 'Transaction', ['Transaction'], { amount: '$1,842.77', merchant: 'Electronics retailer' }),
    node('txn:electronics:merchant', 'Merchant Detail', 'Evidence', ['Evidence', 'TransactionDetail'], { merchant: 'Electronics retailer', category: 'Consumer electronics' }),
    node('risk:freeze', 'Freeze Decision', 'RiskSignal', ['RiskSignal'], { confidence: '83%', action: 'Temporary freeze' }),
    node('risk:freeze:reason', 'Freeze Reason', 'Evidence', ['Evidence', 'RiskDetail'], { reason: 'Merchant anomaly + purchase size' }),
    node('risk:fraud-case', 'Fraud Review', 'RiskSignal', ['RiskSignal', 'Case'], { status: 'Not escalated', sla: 'Same call' }),
    node('account:offset', 'Offset Account', 'Account', ['Account'], { maskedAccount: 'xxxx-7720', linkedLoan: 'Home loan HL-2041' }),
    node('loan:home', 'Home Loan', 'Loan', ['Loan'], { loanId: 'HL-2041', repaymentSource: 'Offset account' }),
    node('payment:home-loan', 'Home Loan Payment', 'Payment', ['Payment'], { scheduledAmount: '$4,280.00', status: 'Rejected' }),
    node('payment:home-loan:record-impact', 'Record Impact', 'Evidence', ['Evidence', 'PaymentDetail'], { impact: 'Preventable', reportingStatus: 'No record impact yet' }),
    node('case:incident', 'Premier Care Case', 'Case', ['Case'], { priority: 'Premier', owner: 'Aria' }),
    node('consent:grace', 'Grace Consent', 'Consent', ['Consent'], { required: 'Yes', capture: 'Voice confirmation' }),
    node('remediation:grace', 'Grace Period', 'Remediation', ['Remediation'], { status: 'Available after consent', duration: '14 days' }),
    node('remediation:grace:expiry', 'Grace Expiry', 'Evidence', ['Evidence', 'RemediationDetail'], { expiry: '14 days from today' }),
    node('consent:digital-card', 'Digital Card Consent', 'Consent', ['Consent'], { required: 'Yes', capture: 'Voice confirmation' }),
    node('card:digital', 'Digital Card', 'Card', ['Card', 'Remediation'], { status: 'Ready to activate', walletSupport: 'Apple Pay, Google Pay' }),
    node('card:digital:wallets', 'Wallet Rails', 'Evidence', ['Evidence', 'CardDetail'], { supportedWallets: 'Apple Pay, Google Pay' }),
    node('fulfilment:physical-card', 'Physical Card Shipment', 'Remediation', ['Remediation', 'Fulfilment'], { method: 'Express post', eta: '1-2 business days' })
  ];
  const links = [];
  for (let i = 0; i < tracePath.length - 1; i += 1) links.push(link(tracePath[i], tracePath[i + 1], 'NEXT_CONTEXT', {}));
  links.push(link('fulfilment:physical-card', 'address:registered', 'SHIPS_ONLY_TO', { guardrail: 'registered address only' }));
  return { nodes, links };
}

function node(id, label, primaryLabel, labels, properties) {
  return { id, label, primaryLabel, labels, properties };
}

function link(source, target, type, properties) {
  return { source, target, type, properties };
}
