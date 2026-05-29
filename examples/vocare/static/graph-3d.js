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

const NODE_TYPES = {
  Customer: { hex: '#f59e0b', rgb: '245,158,11', glyph: 'J' },
  Channel: { hex: '#64748b', rgb: '100,116,139', glyph: 'C' },
  Identity: { hex: '#fbbf24', rgb: '251,191,36', glyph: 'I' },
  Card: { hex: '#3b82f6', rgb: '59,130,246', glyph: 'V' },
  Transaction: { hex: '#38bdf8', rgb: '56,189,248', glyph: '$' },
  RiskSignal: { hex: '#ef4444', rgb: '239,68,68', glyph: 'R' },
  Account: { hex: '#10b981', rgb: '16,185,129', glyph: 'A' },
  Payment: { hex: '#22c55e', rgb: '34,197,94', glyph: 'P' },
  Consent: { hex: '#8b5cf6', rgb: '139,92,246', glyph: 'Y' },
  Remediation: { hex: '#a855f7', rgb: '168,85,247', glyph: '+' },
  Address: { hex: '#f97316', rgb: '249,115,22', glyph: 'H' },
};

const visibleIds = [
  'customer:jack',
  'identity:biometric',
  'device:iphone',
  'card:visa4481',
  'txn:electronics',
  'risk:freeze',
  'payment:home-loan',
  'consent:grace',
  'remediation:grace',
  'card:digital',
  'fulfilment:physical-card',
  'address:registered'
];

const tracePath = [
  'customer:jack',
  'identity:biometric',
  'device:iphone',
  'card:visa4481',
  'txn:electronics',
  'risk:freeze',
  'payment:home-loan',
  'consent:grace',
  'remediation:grace',
  'card:digital',
  'fulfilment:physical-card',
  'address:registered'
];

const traceCopy = {
  'customer:jack': ['Customer anchor', 'Jack is the stable center of the context graph.'],
  'identity:biometric': ['Verification approved', 'The CommBank app push unlocks sensitive account context.'],
  'device:iphone': ['Trusted device', 'The approval came from Jack\'s known CommBank app device.'],
  'card:visa4481': ['Visa freeze found', 'Aria accesses the card only after Jack confirms the topic.'],
  'txn:electronics': ['Purchase trigger', 'The electronics purchase is the transaction Jack needs to confirm.'],
  'risk:freeze': ['Risk signal', 'The freeze decision explains why the card was restricted.'],
  'payment:home-loan': ['Payment impact', 'The rejected home loan payment is surfaced only after consent.'],
  'consent:grace': ['Consent required', 'Aria asks before applying any grace-period action.'],
  'remediation:grace': ['Grace period', 'The protection window is applied after Jack agrees.'],
  'card:digital': ['Digital replacement', 'A replacement digital card can be activated immediately.'],
  'fulfilment:physical-card': ['Physical card', 'The physical card is express-shipped only to the registered address.'],
  'address:registered': ['Address guardrail', 'Aria never sends the card to any other address.']
};

const nodeCallouts = {
  'customer:jack': {
    title: 'Call opened',
    body: 'Aria starts with Jack as the customer anchor. No account information is discussed until verification is complete.',
    meta: 'Premier Banking profile loaded'
  },
  'identity:biometric': {
    title: 'CommBank app push sent',
    body: 'Security notification sent to Jack\'s CommBank app. Aria waits until Jack confirms he approved it before proceeding.',
    meta: 'Biometric push - pending customer confirmation'
  },
  'device:iphone': {
    title: 'Trusted device matched',
    body: 'The approval is linked to Jack\'s known iPhone with a strong trust score and no recent device-risk signals.',
    meta: 'Trust score: Strong'
  },
  'card:visa4481': {
    title: 'Reviewing card status',
    body: 'CommBank Awards Visa ending 4481 is temporarily frozen. Aria checks this only after Jack says he is calling about the card.',
    meta: 'Status: Temporarily frozen'
  },
  'txn:electronics': {
    title: 'Unusual purchase detected',
    body: 'The freeze was triggered by an unusual $1,842.77 electronics purchase this morning. Aria asks Jack whether he made it.',
    meta: 'Amount: $1,842.77'
  },
  'risk:freeze': {
    title: 'Freeze decision reviewed',
    body: 'The risk control was based on merchant anomaly and purchase size. It can be resolved on the call if Jack confirms the purchase.',
    meta: 'Model confidence: 83%'
  },
  'payment:home-loan': {
    title: 'Flow-on impact found',
    body: 'The card freeze affected the linked home loan payment. Aria surfaces this only after Jack confirms the transaction.',
    meta: 'Payment status: Rejected'
  },
  'consent:grace': {
    title: 'Consent required',
    body: 'Aria offers help and waits for Jack to agree before applying the 14-day grace period.',
    meta: 'Capture: Voice confirmation'
  },
  'remediation:grace': {
    title: 'Grace period available',
    body: 'Once Jack agrees, Aria applies the grace period and confirms there will be no record impact inside the window.',
    meta: 'Duration: 14 days'
  },
  'card:digital': {
    title: 'Digital card ready',
    body: 'After Jack agrees, Aria activates the replacement digital card for Apple Pay or Google Pay.',
    meta: 'Availability: Immediate'
  },
  'fulfilment:physical-card': {
    title: 'Physical card prepared',
    body: 'The physical replacement card is express-shipped and should arrive in 1-2 business days.',
    meta: 'Delivery: Express post'
  },
  'address:registered': {
    title: 'Registered address only',
    body: 'Aria confirms the card can only be sent to the registered address on file.',
    meta: 'Guardrail enforced'
  }
};

const demoLines = {
  'identity:biometric': 'Hi Jack, lovely to hear from you. Before we get started, I\'ll need to verify it\'s you. Could you check your CommBank app? There should be a push notification to approve.',
  'card:visa4481': 'Thanks, Jack, you\'re all verified. I can see there\'s been some recent activity on your account. Are you by any chance calling about your Visa credit card?',
  'txn:electronics': 'I\'ll take a look at that for you now.',
  'risk:freeze': 'I\'ve temporarily frozen your CommBank Awards Visa ending in 4481 after an unusual $1,842.77 electronics purchase this morning. Did you make that purchase yourself?'
};

const layout = {
  'customer:jack': { xPct: 50, yPct: 47, z: 0, size: 'lg' },
  'identity:biometric': { xPct: 33, yPct: 28, z: -120, size: 'md', type: 'Channel' },
  'device:iphone': { xPct: 23, yPct: 16, z: -260 },
  'card:visa4481': { xPct: 29, yPct: 52, z: -120, size: 'md', type: 'Channel' },
  'txn:electronics': { xPct: 14, yPct: 40, z: -260 },
  'risk:freeze': { xPct: 14, yPct: 65, z: -260 },
  'payment:home-loan': { xPct: 48, yPct: 78, z: -140, size: 'md', type: 'Channel' },
  'consent:grace': { xPct: 63, yPct: 78, z: -260 },
  'remediation:grace': { xPct: 72, yPct: 62, z: -120, size: 'md', type: 'Channel' },
  'card:digital': { xPct: 83, yPct: 43, z: -260 },
  'fulfilment:physical-card': { xPct: 82, yPct: 22, z: -260 },
  'address:registered': { xPct: 92, yPct: 59, z: -260 },
};

let fullGraphData = { nodes: [], links: [] };
let graphData = { nodes: [], links: [] };
let nodeById = new Map();
let callState = 'idle';
let peerConnection = null;
let dataChannel = null;
let localStream = null;
let localTrack = null;
let remoteAudio = null;
let activePcId = null;
let graphPollTimer = 0;
let pingTimer = 0;
let traceTimer = 0;
let traceIndex = 0;
const transcriptSeen = new Set();

class ContextGraph {
  constructor(worldId, canvasId) {
    this.world = document.getElementById(worldId);
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    this.scene = this.canvas.parentElement;
    this.nodes = [];
    this.edges = [];
    this.nodeMap = new Map();
    this.activeNodes = new Set();
    this.activeEdgeKeys = new Set();
    this.calloutNodeId = null;
    this.calloutEl = document.createElement('div');
    this.calloutEl.className = 'node-callout';
    this.scene.appendChild(this.calloutEl);
    this.dpr = window.devicePixelRatio || 1;
    this.rotX = 0;
    this.rotY = 0;
    this.targetRotX = 0;
    this.targetRotY = 0;
    this.resize();
    window.addEventListener('resize', () => this.resize());
    this.scene.addEventListener('mousemove', (event) => {
      const rect = this.scene.getBoundingClientRect();
      this.targetRotY = ((event.clientX - rect.left) / rect.width - 0.5) * 8;
      this.targetRotX = -((event.clientY - rect.top) / rect.height - 0.5) * 5;
    });
    this.scene.addEventListener('mouseleave', () => {
      this.targetRotX = 0;
      this.targetRotY = 0;
    });
    this.loop();
  }

  resize() {
    const rect = this.scene.getBoundingClientRect();
    this.width = rect.width;
    this.height = rect.height;
    this.canvas.width = this.width * this.dpr;
    this.canvas.height = this.height * this.dpr;
    this.canvas.style.width = `${this.width}px`;
    this.canvas.style.height = `${this.height}px`;
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this.nodes.forEach((node) => this.positionNode(node));
  }

  load(data) {
    this.world.innerHTML = '';
    this.nodes = [];
    this.edges = [];
    this.nodeMap.clear();
    this.activeNodes.clear();
    this.activeEdgeKeys.clear();
    document.getElementById('graphPlaceholder').style.display = 'none';
    this.hideCallout();

    data.nodes.forEach((sourceNode, index) => {
      const position = layout[sourceNode.id];
      if (!position) return;
      const type = position.type || sourceNode.primaryLabel || 'Customer';
      const color = NODE_TYPES[type] || NODE_TYPES[sourceNode.primaryLabel] || NODE_TYPES.Customer;
      const el = document.createElement('div');
      el.className = `graph-node size-${position.size || 'sm'} inactive entering`;
      el.style.setProperty('--node-color', color.hex);
      el.style.setProperty('--node-rgb', color.rgb);
      el.style.setProperty('--start-x', `${this.width / 2}px`);
      el.style.setProperty('--start-y', `${this.height / 2}px`);
      el.innerHTML = `
        <span class="node-glyph">${escapeHtml(color.glyph)}</span>
        <span class="node-label">${escapeHtml(sourceNode.label)}</span>
        <span class="node-sublabel">${escapeHtml(nodeSubtitle(sourceNode))}</span>
      `;
      el.addEventListener('click', () => focusNode(sourceNode.id));
      this.world.appendChild(el);
      const node = { ...sourceNode, el, xPct: position.xPct, yPct: position.yPct, z: position.z, type };
      this.nodes.push(node);
      this.nodeMap.set(node.id, node);
      this.positionNode(node);
      window.setTimeout(() => el.classList.remove('entering'), 700 + index * 20);
    });

    data.links.forEach((link) => {
      const source = this.nodeMap.get(nodeId(link.source));
      const target = this.nodeMap.get(nodeId(link.target));
      if (source && target) this.edges.push({ ...link, source, target, progress: 0, active: false, since: 0 });
    });
    this.activate('customer:jack');
  }

  reset() {
    this.world.innerHTML = '';
    this.nodes = [];
    this.edges = [];
    this.nodeMap.clear();
    this.activeNodes.clear();
    this.activeEdgeKeys.clear();
    this.ctx.clearRect(0, 0, this.width, this.height);
    document.getElementById('graphPlaceholder').style.display = 'flex';
    this.hideCallout();
  }

  positionNode(node) {
    node.x = node.xPct / 100 * this.width;
    node.y = node.yPct / 100 * this.height;
    node.el.style.setProperty('--x', `${node.x}px`);
    node.el.style.setProperty('--y', `${node.y}px`);
    node.el.style.setProperty('--z', `${node.z}px`);
  }

  activate(id) {
    const node = this.nodeMap.get(id);
    if (!node) return;
    this.activeNodes.add(id);
    node.el.classList.remove('inactive', 'dimmed', 'highlighted');
    node.el.classList.add('active');
  }

  traverse(fromId, toId) {
    this.activate(fromId);
    this.activate(toId);
    this.activeEdgeKeys.add(edgeKey(fromId, toId));
    const edge = this.edges.find((candidate) => candidate.source.id === fromId && candidate.target.id === toId);
    if (edge) {
      edge.active = true;
      edge.progress = 0;
      edge.since = performance.now();
    }
  }

  highlight(id) {
    this.nodes.forEach((node) => node.el.classList.toggle('dimmed', node.id !== id && !this.connected(id, node.id)));
    const node = this.nodeMap.get(id);
    if (node) {
      node.el.classList.remove('inactive');
      node.el.classList.add('highlighted');
      window.setTimeout(() => node.el.classList.remove('highlighted'), 1100);
    }
  }

  showCallout(id, detail) {
    const node = this.nodeMap.get(id);
    if (!node || !detail) return;
    this.calloutNodeId = id;
    this.calloutEl.innerHTML = `
      <strong>${escapeHtml(detail.title)}</strong>
      <span>${escapeHtml(detail.body)}</span>
      <em>${escapeHtml(detail.meta || '')}</em>
    `;
    this.calloutEl.classList.add('is-visible');
    this.updateCalloutPosition();
  }

  hideCallout() {
    this.calloutNodeId = null;
    this.calloutEl.classList.remove('is-visible');
  }

  connected(a, b) {
    return this.edges.some((edge) => edge.source.id === a && edge.target.id === b || edge.source.id === b && edge.target.id === a);
  }

  loop() {
    this.rotX += (this.targetRotX - this.rotX) * 0.08;
    this.rotY += (this.targetRotY - this.rotY) * 0.08;
    this.world.style.transform = `rotateX(${this.rotX}deg) rotateY(${this.rotY}deg)`;
    this.drawEdges();
    this.updateCalloutPosition();
    requestAnimationFrame(() => this.loop());
  }

  nodeCenter(node) {
    const nodeRect = node.el.getBoundingClientRect();
    const sceneRect = this.scene.getBoundingClientRect();
    return {
      x: nodeRect.left + nodeRect.width / 2 - sceneRect.left,
      y: nodeRect.top + nodeRect.height / 2 - sceneRect.top,
      radius: Math.min(nodeRect.width, nodeRect.height) / 2
    };
  }

  updateCalloutPosition() {
    if (!this.calloutNodeId || !this.calloutEl.classList.contains('is-visible')) return;
    const node = this.nodeMap.get(this.calloutNodeId);
    if (!node) return;
    const center = this.nodeCenter(node);
    const preferLeft = center.x > this.width * 0.68;
    const x = preferLeft ? center.x - 312 : center.x + center.radius + 18;
    const y = Math.max(72, Math.min(this.height - 170, center.y - 58));
    this.calloutEl.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
    this.calloutEl.classList.toggle('left', preferLeft);
  }

  drawEdges() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.width, this.height);
    this.edges.forEach((edge) => {
      const sourceCenter = this.nodeCenter(edge.source);
      const targetCenter = this.nodeCenter(edge.target);
      const sx = sourceCenter.x;
      const sy = sourceCenter.y;
      const tx = targetCenter.x;
      const ty = targetCenter.y;
      const dx = tx - sx;
      const dy = ty - sy;
      const len = Math.max(1, Math.sqrt(dx * dx + dy * dy));
      const cx = (sx + tx) / 2 + (-dy / len) * Math.min(60, len * 0.14);
      const cy = (sy + ty) / 2 + (dx / len) * Math.min(60, len * 0.14);
      const active = edge.active || this.activeEdgeKeys.has(edgeKey(edge.source.id, edge.target.id));
      const color = NODE_TYPES[edge.target.type]?.hex || NODE_TYPES[edge.target.primaryLabel]?.hex || '#64748b';

      if (edge.active) edge.progress = Math.min(1, (performance.now() - edge.since) / 620);
      ctx.save();
      ctx.strokeStyle = active ? color : '#1b1b1b';
      ctx.lineWidth = active ? 2.4 : 1;
      ctx.globalAlpha = active ? 0.86 : 0.36;
      ctx.shadowColor = active ? color : 'transparent';
      ctx.shadowBlur = active ? 12 : 0;
      ctx.beginPath();
      if (edge.active && edge.progress < 1) {
        drawPartialQuad(ctx, sx, sy, cx, cy, tx, ty, edge.progress);
      } else {
        ctx.moveTo(sx, sy);
        ctx.quadraticCurveTo(cx, cy, tx, ty);
      }
      ctx.stroke();
      ctx.restore();
    });
  }
}

const graphRenderer = new ContextGraph('graphWorld', 'edgeCanvas');

initialize();

async function initialize() {
  refreshButton.addEventListener('click', loadGraph);
  traceButton.addEventListener('click', runTraceDemo);
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
      const query = normalize(searchInput.value);
      const match = graphData.nodes.find((node) => normalize(node.label).includes(query) || normalize(node.id).includes(query));
      if (match) focusNode(match.id);
    }
  });
  window.addEventListener('pagehide', () => disconnectCall(true));
  await loadGraph();
}

async function loadGraph() {
  statusText.textContent = 'Loading context...';
  try {
    const limit = Number(limitInput.value || 2500);
    const response = await fetch(`/api/graph/visualization?limit=${encodeURIComponent(limit)}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    fullGraphData = normalizePayload(await response.json());
  } catch (_) {
    fullGraphData = mockGraphData();
  }
  graphData = reduceGraph(fullGraphData);
  nodeById = new Map(graphData.nodes.map((node) => [node.id, node]));
  nodeCount.textContent = graphData.nodes.length;
  linkCount.textContent = graphData.links.length;
  renderLegend();
  renderAccessPath();
  graphRenderer.reset();
  showNodeDetails(graphData.nodes[0]);
  statusText.textContent = 'Context ready - waiting for call';
}

function reduceGraph(data) {
  const nodes = visibleIds.map((id) => data.nodes.find((node) => node.id === id)).filter(Boolean);
  const nodeIds = new Set(nodes.map((node) => node.id));
  const apiLinks = data.links.filter((link) => nodeIds.has(nodeId(link.source)) && nodeIds.has(nodeId(link.target)));
  const links = [];
  for (let i = 0; i < tracePath.length - 1; i += 1) {
    const source = tracePath[i];
    const target = tracePath[i + 1];
    if (!nodeIds.has(source) || !nodeIds.has(target)) continue;
    const existing = apiLinks.find((link) => nodeId(link.source) === source && nodeId(link.target) === target);
    links.push(existing || { source, target, type: 'ACCESSES', properties: {} });
  }
  return { nodes, links };
}

function runTraceDemo() {
  if (traceTimer) {
    clearInterval(traceTimer);
    traceTimer = 0;
    traceButton.classList.remove('is-running');
    return;
  }
  graphRenderer.load(graphData);
  statusText.textContent = 'Traversing graph...';
  traceButton.classList.add('is-running');
  traceIndex = 0;
  focusNode(tracePath[0], false);
  traceTimer = setInterval(() => {
    const fromId = tracePath[traceIndex];
    const toId = tracePath[traceIndex + 1];
    if (!toId) {
      clearInterval(traceTimer);
      traceTimer = 0;
      traceButton.classList.remove('is-running');
      statusText.textContent = 'Context loaded - agent has full awareness';
      return;
    }
    graphRenderer.traverse(fromId, toId);
    if (demoLines[toId]) addTranscript('agent', demoLines[toId]);
    focusNode(toId, false);
    traceIndex += 1;
  }, 560);
}

function focusNode(id, highlight = true) {
  const node = nodeById.get(id);
  if (!node) return;
  if (highlight) graphRenderer.highlight(id);
  graphRenderer.activate(id);
  graphRenderer.showCallout(id, nodeCallouts[id]);
  showNodeDetails(node);
  renderAccessPath(id);
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
  const targetId = map[id] || id;
  const targetIndex = tracePath.indexOf(targetId);
  if (targetIndex > 0) {
    graphRenderer.traverse(tracePath[targetIndex - 1], targetId);
  }
  focusNode(targetId);
}

async function connectCall() {
  if (callState === 'connecting' || callState === 'connected') return;
  setCallState('connecting', 'Requesting microphone...');
  clearTranscript();
  graphRenderer.load(graphData);
  statusText.textContent = 'Context graph expanding...';

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
        statusText.textContent = 'Context loaded - agent has full awareness';
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
  line.textContent = cleanText;
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

function renderLegend() {
  const types = [...new Set(graphData.nodes.map((node) => layout[node.id]?.type || node.primaryLabel))];
  legendEl.innerHTML = types.map((type) => {
    const color = NODE_TYPES[type] || NODE_TYPES.Customer;
    return `<div class="legend-item"><span class="legend-dot" style="background:${color.hex}"></span>${escapeHtml(type)}</div>`;
  }).join('');
}

function renderAccessPath(activeId = 'customer:jack') {
  accessPathEl.innerHTML = tracePath.map((id) => {
    const node = nodeById.get(id);
    if (!node) return '';
    return `<div class="path-item${id === activeId ? ' active' : ''}"><span class="swatch"></span>${escapeHtml(node.label)}</div>`;
  }).join('');
}

function propertyTable(properties) {
  const rows = Object.entries(properties || {})
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `<tr><th>${escapeHtml(key)}</th><td>${escapeHtml(formatValue(value))}</td></tr>`)
    .join('');
  return rows ? `<table>${rows}</table>` : '<p class="muted">No properties.</p>';
}

function nodeSubtitle(node) {
  if (node.id === 'customer:jack') return node.properties.segment || 'Premier';
  if (node.primaryLabel === 'Evidence') return node.labels?.[1] || 'Evidence';
  if (node.properties.status) return node.properties.status;
  if (node.properties.amount) return node.properties.amount;
  if (node.properties.method) return node.properties.method;
  return node.primaryLabel;
}

function edgeKey(source, target) {
  return `${source}->${target}`;
}

function nodeId(value) {
  return value && typeof value === 'object' ? value.id : value;
}

function drawPartialQuad(ctx, x0, y0, cx, cy, x1, y1, t) {
  if (t >= 1) {
    ctx.moveTo(x0, y0);
    ctx.quadraticCurveTo(cx, cy, x1, y1);
    return;
  }
  const ax = x0 + (cx - x0) * t;
  const ay = y0 + (cy - y0) * t;
  const bx = cx + (x1 - cx) * t;
  const by = cy + (y1 - cy) * t;
  const ex = ax + (bx - ax) * t;
  const ey = ay + (by - ay) * t;
  ctx.moveTo(x0, y0);
  ctx.quadraticCurveTo(ax, ay, ex, ey);
}

function normalize(value) {
  return String(value || '').toLowerCase().trim();
}

function formatValue(value) {
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
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
  const fallback = {
    'customer:jack': ['Jack Thompson', 'Customer', ['Customer', 'Premier'], { segment: 'Premier Banking', relationshipSince: '2016' }],
    'identity:biometric': ['Biometric Push', 'Identity', ['Identity', 'SecurityControl'], { status: 'Approved', confidence: '99.6%' }],
    'device:iphone': ['Trusted iPhone', 'Identity', ['Device', 'Security'], { device: 'iPhone 15 Pro', trustScore: 'Strong' }],
    'card:visa4481': ['Awards Visa 4481', 'Card', ['Card'], { status: 'Temporarily frozen', lastFour: '4481' }],
    'txn:electronics': ['Electronics Purchase', 'Transaction', ['Transaction'], { amount: '$1,842.77', merchant: 'Electronics retailer' }],
    'risk:freeze': ['Freeze Decision', 'RiskSignal', ['RiskSignal'], { action: 'Temporary freeze', confidence: '83%' }],
    'payment:home-loan': ['Home Loan Payment', 'Payment', ['Payment'], { status: 'Rejected', scheduledAmount: '$4,280.00' }],
    'consent:grace': ['Grace Consent', 'Consent', ['Consent'], { required: 'Yes', capture: 'Voice confirmation' }],
    'remediation:grace': ['Grace Period', 'Remediation', ['Remediation'], { duration: '14 days', status: 'Available after consent' }],
    'card:digital': ['Digital Card', 'Card', ['Card', 'Remediation'], { status: 'Ready to activate', walletSupport: 'Apple Pay, Google Pay' }],
    'fulfilment:physical-card': ['Physical Card', 'Remediation', ['Remediation', 'Fulfilment'], { method: 'Express post', eta: '1-2 business days' }],
    'address:registered': ['Registered Address', 'Address', ['Address', 'PersonalInfo'], { usage: 'Card fulfilment only', guardrail: 'Registered address only' }]
  };
  const nodes = visibleIds.map((id) => {
    const [label, primaryLabel, labels, properties] = fallback[id];
    return { id, label, primaryLabel, labels, properties };
  });
  const links = tracePath.slice(0, -1).map((id, index) => ({ source: id, target: tracePath[index + 1], type: 'ACCESSES', properties: {} }));
  return { nodes, links };
}
