const graphEl = document.querySelector('#graph');
const statusText = document.querySelector('#statusText');
const nodeCount = document.querySelector('#nodeCount');
const linkCount = document.querySelector('#linkCount');
const selectionDetails = document.querySelector('#selectionDetails');
const legendEl = document.querySelector('#legend');
const accessPathEl = document.querySelector('#accessPath');
const limitInput = document.querySelector('#limitInput');
const labelsToggle = document.querySelector('#labelsToggle');
const searchInput = document.querySelector('#searchInput');
const refreshButton = document.querySelector('#refreshButton');
const traceButton = document.querySelector('#traceButton');
const callButton = document.querySelector('#callButton');
const talkButton = document.querySelector('#talkButton');
const hangupButton = document.querySelector('#hangupButton');
const callStatus = document.querySelector('#callStatus');
const callTranscript = document.querySelector('#callTranscript');

const palette = [
  '#60a5fa',
  '#34d399',
  '#f59e0b',
  '#f87171',
  '#a78bfa',
  '#2dd4bf',
  '#f472b6',
  '#c084fc',
  '#fb7185',
  '#a3e635',
  '#38bdf8',
  '#facc15'
];

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
  'customer:jack': {
    title: 'Call context opened',
    text: 'Aria starts with Jack as the stable customer anchor before any account data is discussed.'
  },
  'identity:biometric': {
    title: 'Verification approved',
    text: 'The app push confirms Jack before Aria can access sensitive information.'
  },
  'identity:biometric:confidence': {
    title: 'Confidence checked',
    text: 'Aria checks the confidence score attached to the biometric approval.'
  },
  'identity:biometric:timestamp': {
    title: 'Approval timing checked',
    text: 'The approval timestamp confirms this verification belongs to the current call.'
  },
  'identity:kyc': {
    title: 'Identity profile checked',
    text: 'KYC status confirms this is a low-risk verified customer record.'
  },
  'identity:passport': {
    title: 'Document match',
    text: 'Stored identity documents support the verified customer context.'
  },
  'contact:mobile': {
    title: 'Trusted contact point',
    text: 'The verified mobile number links the push approval back to Jack.'
  },
  'contact:mobile:push-channel': {
    title: 'Push channel confirmed',
    text: 'The graph confirms the app push channel is the preferred verification route.'
  },
  'contact:email': {
    title: 'Digital contact preference',
    text: 'Aria can see statement and digital communication preferences.'
  },
  'device:iphone': {
    title: 'Trusted device',
    text: 'The approval came from a known CommBank app device.'
  },
  'device:iphone:trust-score': {
    title: 'Device trust score',
    text: 'Aria checks that the device trust score is strong before proceeding.'
  },
  'address:registered': {
    title: 'Registered address guardrail',
    text: 'Card fulfilment must use this address only.'
  },
  'profile:premier': {
    title: 'Premier relationship',
    text: 'Aria uses the relationship profile to keep the interaction calm and concise.'
  },
  'card:visa4481': {
    title: 'Visa card freeze',
    text: 'The affected card is retrieved after Jack confirms he is calling about it.'
  },
  'card:visa4481:status': {
    title: 'Freeze status read',
    text: 'The card status node confirms the Visa is temporarily frozen.'
  },
  'txn:electronics': {
    title: 'Purchase trigger',
    text: 'The transaction that caused the freeze is shown so Aria can ask whether Jack made it.'
  },
  'txn:electronics:merchant': {
    title: 'Merchant detail read',
    text: 'Aria checks the merchant and amount before asking Jack to confirm the purchase.'
  },
  'risk:freeze': {
    title: 'Risk signal',
    text: 'The freeze decision explains why the card was temporarily restricted.'
  },
  'risk:freeze:reason': {
    title: 'Freeze reason read',
    text: 'The model reason explains why the automated freeze was triggered.'
  },
  'risk:fraud-case': {
    title: 'Review state',
    text: 'Fraud review is present but not escalated because Jack can confirm the transaction.'
  },
  'account:offset': {
    title: 'Linked offset account',
    text: 'Aria follows the graph to the account affected by the freeze workflow.'
  },
  'loan:home': {
    title: 'Home loan context',
    text: 'The offset account is tied to Jack’s home loan repayment.'
  },
  'payment:home-loan': {
    title: 'Rejected payment impact',
    text: 'The home loan payment impact is surfaced only after Jack confirms the purchase.'
  },
  'payment:home-loan:record-impact': {
    title: 'Record impact checked',
    text: 'Aria checks whether the rejected payment can still be protected.'
  },
  'case:incident': {
    title: 'Premier care case',
    text: 'A service case pulls the card, payment, consent, and remediation context together.'
  },
  'consent:grace': {
    title: 'Grace consent required',
    text: 'Aria must ask before applying the grace period.'
  },
  'remediation:grace': {
    title: 'Grace period applied',
    text: 'Once Jack agrees, the 14-day grace period prevents record impact.'
  },
  'remediation:grace:expiry': {
    title: 'Grace expiry calculated',
    text: 'The expiry node gives Aria the exact date to confirm back to Jack.'
  },
  'consent:digital-card': {
    title: 'Digital card consent',
    text: 'Aria asks before activating a replacement digital card.'
  },
  'card:digital': {
    title: 'Digital card active',
    text: 'The replacement card can be used immediately in Apple Pay or Google Pay.'
  },
  'card:digital:wallets': {
    title: 'Wallet compatibility checked',
    text: 'Aria checks wallet compatibility before explaining immediate use.'
  },
  'fulfilment:physical-card': {
    title: 'Physical card shipment',
    text: 'The physical card is express-shipped to the registered address only.'
  }
};

let graph;
let fullGraphData = { nodes: [], links: [] };
let graphData = { nodes: [], links: [] };
let colorByLabel = new Map();
let centerNode = null;
let activeTraceNodeId = 'customer:jack';
let visibleNodeIds = new Set();
let keyboardAnimationId = 0;
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
const activeKeys = new Set();
const centerPosition = new THREE.Vector3(0, 0, 0);

initialize();

async function initialize() {
  graph = ForceGraph3D()(graphEl)
    .backgroundColor('#090b10')
    .nodeLabel((node) => `${node.label}<br>${node.labels?.join(', ') || ''}`)
    .nodeColor((node) => colorForLabel(node.primaryLabel))
    .nodeVal((node) => nodeSize(node))
    .linkColor((link) => activeTraceLink(link) ? 'rgba(245, 158, 11, 0.88)' : traceLink(link) ? 'rgba(245, 158, 11, 0.36)' : 'rgba(170, 190, 220, 0.22)')
    .linkOpacity(0.55)
    .linkWidth((link) => activeTraceLink(link) ? 2.6 : traceLink(link) ? 1.35 : importantRelationship(link) ? 0.95 : 0.45)
    .linkDirectionalParticles((link) => activeTraceLink(link) ? 2 : 0)
    .linkDirectionalParticleWidth(2.2)
    .linkDirectionalParticleSpeed(0.004)
    .linkLabel((link) => link.type)
    .onNodeClick(focusNode)
    .onLinkClick(showLinkDetails);

  graph.d3Force('charge').strength(-38);
  graph.d3Force('link').distance((link) => traceLink(link) ? 58 : importantRelationship(link) ? 72 : 118);
  graph.d3VelocityDecay(0.58);
  graph.cooldownTicks(80);

  labelsToggle.addEventListener('change', renderGraph);
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
  window.addEventListener('keydown', handleKeyDown);
  window.addEventListener('keyup', handleKeyUp);
  window.addEventListener('blur', () => activeKeys.clear());
  window.addEventListener('pagehide', () => disconnectCall(true));
  window.addEventListener('resize', resizeGraph);

  resizeGraph();
  await loadGraph();
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
  if (graphPollTimer) {
    clearInterval(graphPollTimer);
    graphPollTimer = 0;
  }
  if (pingTimer) {
    clearInterval(pingTimer);
    pingTimer = 0;
  }
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
  if (transcriptSeen.size > 80) {
    const oldest = transcriptSeen.values().next().value;
    transcriptSeen.delete(oldest);
  }

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
  const node = fullGraphData.nodes.find((candidate) => candidate.id === targetId);
  if (node) focusNode(node);
}

async function loadGraph() {
  const limit = Math.max(100, Math.min(10000, Number(limitInput.value || 2500)));
  statusText.textContent = 'Loading...';
  refreshButton.disabled = true;

  try {
    const response = await fetch(`/api/graph/visualization?limit=${encodeURIComponent(limit)}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    fullGraphData = normalizePayload(payload);
    statusText.textContent = `Loaded ${formatNumber(fullGraphData.links.length)} relationships`;
  } catch (error) {
    fullGraphData = mockGraphData();
    statusText.textContent = `Mock graph: ${formatNumber(fullGraphData.links.length)} relationships`;
  } finally {
    applyRadialLayout(fullGraphData);
    colorByLabel = buildColorMap(fullGraphData.nodes);
    centerNode = fullGraphData.nodes.find((node) => node.id === 'customer:jack') || findDefaultCenterNode(fullGraphData);
    pinCenterNode(centerNode);
    renderLegend();
    beginStarExpansion();
    showNodeDetails(centerNode);
    renderAccessPath(centerNode?.id);
    setCameraOrbitCenter(false);
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

function renderGraph() {
  graph.nodeThreeObject(labelsToggle.checked ? labelObject : null);
  graph.graphData(graphData);
}

function beginStarExpansion() {
  if (starTimer) {
    clearInterval(starTimer);
    starTimer = 0;
  }
  activeTraceNodeId = centerNode?.id || 'customer:jack';
  visibleNodeIds = new Set([activeTraceNodeId]);
  updateVisibleGraph();

  const orderedIds = expansionOrder();
  let index = 0;
  starTimer = setInterval(() => {
    const batchSize = index < 12 ? 2 : 4;
    for (let i = 0; i < batchSize && index < orderedIds.length; i += 1) {
      visibleNodeIds.add(orderedIds[index]);
      index += 1;
    }
    updateVisibleGraph();
    if (index >= orderedIds.length) {
      clearInterval(starTimer);
      starTimer = 0;
    }
  }, 95);
}

function expansionOrder() {
  const ids = new Set(fullGraphData.nodes.map((node) => node.id));
  const first = tracePath.filter((id) => ids.has(id) && id !== centerNode?.id);
  const linkedToCustomer = fullGraphData.links
    .filter((link) => nodeId(link.source) === 'customer:jack' || nodeId(link.target) === 'customer:jack')
    .map((link) => nodeId(link.source) === 'customer:jack' ? nodeId(link.target) : nodeId(link.source))
    .filter((id) => ids.has(id) && !first.includes(id) && id !== centerNode?.id);
  const rest = fullGraphData.nodes
    .map((node) => node.id)
    .filter((id) => id !== centerNode?.id && !first.includes(id) && !linkedToCustomer.includes(id));
  return [...first, ...linkedToCustomer, ...rest];
}

function updateVisibleGraph() {
  graphData = {
    nodes: fullGraphData.nodes.filter((node) => visibleNodeIds.has(node.id)),
    links: fullGraphData.links.filter((link) => visibleNodeIds.has(nodeId(link.source)) && visibleNodeIds.has(nodeId(link.target)))
  };
  renderGraph();
}

function revealNodeAndContext(nodeIdToReveal) {
  if (!nodeIdToReveal) return;
  const pathIndex = tracePath.indexOf(nodeIdToReveal);
  if (pathIndex >= 0) {
    tracePath.slice(0, pathIndex + 1).forEach((id) => visibleNodeIds.add(id));
  }
  visibleNodeIds.add(nodeIdToReveal);

  for (const link of fullGraphData.links) {
    const source = nodeId(link.source);
    const target = nodeId(link.target);
    if (source === nodeIdToReveal && (target.startsWith(`${nodeIdToReveal}:`) || tracePath.includes(target))) {
      visibleNodeIds.add(target);
    }
    if (target === nodeIdToReveal && (source.startsWith(`${nodeIdToReveal}:`) || tracePath.includes(source))) {
      visibleNodeIds.add(source);
    }
  }
  updateVisibleGraph();
}

function labelObject(node) {
  const group = new THREE.Group();
  const size = nodeSize(node);
  const color = colorForLabel(node.primaryLabel);
  const isActive = node.id === activeTraceNodeId;
  const geometry = new THREE.SphereGeometry(size, 18, 18);
  const material = new THREE.MeshLambertMaterial({
    color,
    emissive: color,
    emissiveIntensity: isActive ? 0.72 : tracePath.includes(node.id) ? 0.32 : 0.1
  });
  group.add(new THREE.Mesh(geometry, material));

  if (tracePath.includes(node.id)) {
    const halo = new THREE.Mesh(
      new THREE.SphereGeometry(size * (isActive ? 2.25 : 1.55), 18, 18),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: isActive ? 0.16 : 0.07 })
    );
    group.add(halo);
  }

  const sprite = new SpriteText(node.label);
  sprite.color = '#f4f7fb';
  sprite.textHeight = node.id === 'customer:jack' ? 5.8 : 4.5;
  sprite.position.y = size + 4;
  group.add(sprite);
  return group;
}

function focusNode(node) {
  if (!node) return;
  revealNodeAndContext(node.id);
  activeTraceNodeId = node.id;
  const visibleNode = graphData.nodes.find((candidate) => candidate.id === node.id) || node;
  showNodeDetails(visibleNode);
  renderAccessPath(node.id);
  flyToNode(visibleNode);
  renderGraph();
}

function showNodeDetails(node) {
  const copy = traceCopy[node.id];
  selectionDetails.innerHTML = [
    `<h3>${escapeHtml(node.label)}</h3>`,
    `<p class="muted">${escapeHtml(node.labels?.join(', ') || node.primaryLabel)}</p>`,
    copy ? `<div class="trace-note"><strong>${escapeHtml(copy.title)}</strong><span>${escapeHtml(copy.text)}</span></div>` : '',
    propertyTable({ id: node.id, ...node.properties })
  ].join('');
}

function showLinkDetails(link) {
  const sourceId = nodeId(link.source);
  const targetId = nodeId(link.target);
  selectionDetails.innerHTML = [
    `<h3>${escapeHtml(link.type)}</h3>`,
    propertyTable({
      source: nodeLabel(sourceId),
      target: nodeLabel(targetId),
      ...link.properties
    })
  ].join('');
  renderAccessPath(targetId);
}

function focusSearchResult() {
  const query = normalize(searchInput.value);
  if (!query) return;
  const node = fullGraphData.nodes.find((candidate) => {
    const values = [candidate.label, candidate.primaryLabel, ...(candidate.labels || []), ...Object.values(candidate.properties || {})];
    return values.some((value) => normalize(value).includes(query));
  });
  if (node) {
    focusNode(node);
    statusText.textContent = `Focused ${node.label}`;
  } else {
    statusText.textContent = 'No matching node';
  }
}

function toggleTrace() {
  if (traceTimer) {
    clearInterval(traceTimer);
    traceTimer = 0;
    traceButton.classList.remove('is-running');
    traceButton.textContent = 'Aria trace';
    return;
  }
  traceIndex = 0;
  traceButton.classList.add('is-running');
  traceButton.textContent = 'Stop trace';
  stepTrace();
  traceTimer = setInterval(stepTrace, 1250);
}

function stepTrace() {
  const id = tracePath[traceIndex % tracePath.length];
  const node = fullGraphData.nodes.find((candidate) => candidate.id === id);
  if (node) {
    focusNode(node);
    statusText.textContent = traceCopy[id]?.title || `Aria accessing ${node.label}`;
  }
  traceIndex += 1;
}

function handleKeyDown(event) {
  if (isTypingTarget(event.target)) return;
  const key = normalizeKey(event.key);
  if (!movementKeys().has(key)) return;
  event.preventDefault();
  activeKeys.add(key);
  if (!keyboardAnimationId) keyboardAnimationId = requestAnimationFrame(stepKeyboardCamera);
}

function handleKeyUp(event) {
  activeKeys.delete(normalizeKey(event.key));
}

function stepKeyboardCamera() {
  keyboardAnimationId = 0;
  if (!activeKeys.size) return;

  const camera = graph.camera();
  const controls = graph.controls();
  const position = camera.position;
  const speed = activeKeys.has('shift') ? 20 : 7;
  const zoomSpeed = activeKeys.has('shift') ? 1.18 : 1.08;

  const spherical = new THREE.Spherical().setFromVector3(new THREE.Vector3().subVectors(position, centerPosition));
  if (activeKeys.has('a') || activeKeys.has('arrowleft')) spherical.theta -= speed * 0.006;
  if (activeKeys.has('d') || activeKeys.has('arrowright')) spherical.theta += speed * 0.006;
  if (activeKeys.has('w') || activeKeys.has('arrowup')) spherical.phi -= speed * 0.004;
  if (activeKeys.has('s') || activeKeys.has('arrowdown')) spherical.phi += speed * 0.004;
  if (activeKeys.has('e')) spherical.phi -= speed * 0.006;
  if (activeKeys.has('q')) spherical.phi += speed * 0.006;
  spherical.phi = Math.max(0.08, Math.min(Math.PI - 0.08, spherical.phi));

  if (activeKeys.has('+') || activeKeys.has('=')) spherical.radius = Math.max(20, spherical.radius / zoomSpeed);
  if (activeKeys.has('-') || activeKeys.has('_')) spherical.radius = Math.min(5000, spherical.radius * zoomSpeed);

  position.copy(centerPosition).add(new THREE.Vector3().setFromSpherical(spherical));
  controls.target.copy(centerPosition);
  controls.update();
  keyboardAnimationId = requestAnimationFrame(stepKeyboardCamera);
}

function movementKeys() {
  return new Set(['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright', 'q', 'e', '+', '=', '-', '_', 'shift']);
}

function normalizeKey(key) {
  return key === 'Shift' ? 'shift' : String(key || '').toLowerCase();
}

function isTypingTarget(target) {
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(target?.tagName) || target?.isContentEditable;
}

function setCenterNode(node) {
  if (!node) return;
  releaseCenterNode();
  centerNode = node;
  pinCenterNode(centerNode);
  setCameraOrbitCenter(true);
  graph.d3ReheatSimulation();
}

function releaseCenterNode() {
  if (!centerNode) return;
  delete centerNode.fx;
  delete centerNode.fy;
  delete centerNode.fz;
}

function pinCenterNode(node) {
  if (!node) return;
  node.x = 0;
  node.y = 0;
  node.z = 0;
  node.fx = 0;
  node.fy = 0;
  node.fz = 0;
}

function setCameraOrbitCenter(animate) {
  const camera = graph.camera();
  const controls = graph.controls();
  const currentOffset = new THREE.Vector3().subVectors(camera.position, controls.target);
  const fallbackOffset = new THREE.Vector3(0, 0, 260);
  const offset = currentOffset.lengthSq() ? currentOffset : fallbackOffset;
  controls.target.copy(centerPosition);
  graph.cameraPosition(centerPosition.clone().add(offset), centerPosition, animate ? 800 : 0);
}

function findDefaultCenterNode(data) {
  const degree = new Map();
  for (const link of data.links || []) {
    const sourceId = nodeId(link.source);
    const targetId = nodeId(link.target);
    degree.set(sourceId, (degree.get(sourceId) || 0) + 1);
    degree.set(targetId, (degree.get(targetId) || 0) + 1);
  }
  return [...(data.nodes || [])].sort((a, b) => (degree.get(b.id) || 0) - (degree.get(a.id) || 0))[0] || null;
}

function nodeLabel(value) {
  if (value && typeof value === 'object') return value.label || value.id;
  return fullGraphData.nodes.find((node) => node.id === value)?.label || value;
}

function nodeId(value) {
  return value && typeof value === 'object' ? value.id : value;
}

function nodeSize(node) {
  if (node.id === activeTraceNodeId) return node.id === 'customer:jack' ? 9 : 6.8;
  if (node.id === 'customer:jack') return 8;
  if (tracePath.includes(node.id)) return 5.2;
  if (node.primaryLabel === 'RiskSignal' || node.primaryLabel === 'Payment') return 5;
  if (node.primaryLabel === 'Identity' || node.primaryLabel === 'Card') return 4.7;
  return 3.7;
}

function importantRelationship(link) {
  return ['CAUSED_REJECTION', 'TRIGGERED_SIGNAL', 'ELIGIBLE_FOR', 'REQUIRES_CONSENT', 'SHIPS_ONLY_TO'].includes(link.type);
}

function traceLink(link) {
  const sourceIndex = tracePath.indexOf(nodeId(link.source));
  const targetIndex = tracePath.indexOf(nodeId(link.target));
  return sourceIndex >= 0 && targetIndex === sourceIndex + 1;
}

function activeTraceLink(link) {
  const targetIndex = tracePath.indexOf(activeTraceNodeId);
  if (targetIndex <= 0) return false;
  return nodeId(link.source) === tracePath[targetIndex - 1] && nodeId(link.target) === activeTraceNodeId;
}

function flyToNode(node) {
  const target = new THREE.Vector3(node.x || 0, node.y || 0, node.z || 0);
  const direction = target.lengthSq() ? target.clone().normalize() : new THREE.Vector3(0, 0, 1);
  const cameraPosition = target.clone().add(direction.multiplyScalar(210)).add(new THREE.Vector3(0, 52, 95));
  graph.cameraPosition(cameraPosition, target, 950);
}

function applyRadialLayout(data) {
  const center = data.nodes.find((node) => node.id === 'customer:jack') || data.nodes[0];
  if (center) {
    center.x = 0;
    center.y = 0;
    center.z = 0;
  }

  const traceSet = new Set(tracePath);
  const rings = new Map();
  for (const node of data.nodes) {
    if (node.id === center?.id) continue;
    const ring = node.id.includes(':') && !traceSet.has(node.id)
      ? node.id.split(':').slice(0, -1).join(':')
      : traceSet.has(node.id)
        ? 'trace'
        : node.primaryLabel || 'Context';
    if (!rings.has(ring)) rings.set(ring, []);
    rings.get(ring).push(node);
  }

  const ringEntries = [...rings.entries()];
  ringEntries.forEach(([ring, nodes], ringIndex) => {
      const parent = data.nodes.find((candidate) => candidate.id === ring);
      const baseRadius = parent ? 28 : ring === 'trace' ? 95 : 145 + ringIndex * 22;
      nodes.forEach((node, index) => {
        const traceIndexForNode = tracePath.indexOf(node.id);
        const angle = ring === 'trace'
          ? (traceIndexForNode / Math.max(1, tracePath.length - 1)) * Math.PI * 1.65 - Math.PI * 0.82
          : (index / nodes.length) * Math.PI * 2 + ringIndex * 0.45;
      const radius = ring === 'trace' ? baseRadius + traceIndexForNode * 8 : baseRadius + (index % 5) * 10;
      const originX = parent?.x || 0;
      const originY = parent?.y || 0;
      const originZ = parent?.z || 0;
      node.x = originX + Math.cos(angle) * radius;
      node.y = originY + Math.sin(angle) * radius * 0.72;
      node.z = originZ + (parent ? ((index % 3) - 1) * 18 : ring === 'trace' ? (traceIndexForNode % 5 - 2) * 24 : ((index + ringIndex) % 7 - 3) * 30);
    });
  });
}

function buildColorMap(nodes) {
  const labels = [...new Set(nodes.map((node) => node.primaryLabel || 'Node'))].sort();
  return new Map(labels.map((label, index) => [label, palette[index % palette.length]]));
}

function colorForLabel(label) {
  return colorByLabel.get(label || 'Node') || '#94a3b8';
}

function renderLegend() {
  legendEl.innerHTML = [...colorByLabel.entries()]
    .map(([label, color]) => `<div class="legend-item"><span class="swatch" style="background:${color}"></span>${escapeHtml(label)}</div>`)
    .join('');
}

function renderAccessPath(activeId) {
  accessPathEl.innerHTML = tracePath
    .filter((id) => graphData.nodes.some((node) => node.id === id))
    .map((id) => {
      const node = graphData.nodes.find((candidate) => candidate.id === id);
      const active = id === activeId ? ' active' : '';
      return `<div class="path-item${active}"><span class="swatch" style="background:${colorForLabel(node.primaryLabel)}"></span>${escapeHtml(node.label)}</div>`;
    })
    .join('');
}

function propertyTable(properties) {
  const rows = Object.entries(properties || {})
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `<tr><th>${escapeHtml(key)}</th><td>${escapeHtml(formatValue(value))}</td></tr>`)
    .join('');
  return rows ? `<table>${rows}</table>` : '<p class="muted">No properties.</p>';
}

function formatValue(value) {
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function resizeGraph() {
  graph.width(graphEl.clientWidth);
  graph.height(graphEl.clientHeight);
}

function normalize(value) {
  return String(value || '').toLowerCase().trim();
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
    node('customer:jack', 'Jack Thompson', 'Customer', ['Customer', 'Premier'], { cif: 'CBA-PRM-882914', segment: 'Premier Banking', relationshipSince: '2016-04-18', currentIntent: 'Calling about Visa card disruption' }),
    node('identity:biometric', 'Biometric Push', 'Identity', ['Identity', 'SecurityControl'], { method: 'CommBank app biometric approval', status: 'Approved', approvedAt: 'Today 10:14:22 AEST', confidence: '99.6%' }),
    node('identity:biometric:confidence', 'Biometric Confidence', 'Evidence', ['Evidence', 'VerificationDetail'], { score: '99.6%', threshold: '95%', decision: 'Pass' }),
    node('identity:biometric:timestamp', 'Approval Timestamp', 'Evidence', ['Evidence', 'VerificationDetail'], { approvedAt: 'Today 10:14:22 AEST', freshness: 'Current call', expiry: 'Single session' }),
    node('identity:kyc', 'KYC Profile', 'Identity', ['Identity', 'KYC'], { status: 'Current', lastReviewed: '2026-02-11', politicallyExposed: 'No', riskTier: 'Low' }),
    node('identity:passport', 'Passport Record', 'Identity', ['Identity', 'Document'], { documentType: 'Passport', verification: 'Matched on file', expiry: '2029-08-03' }),
    node('contact:mobile', 'Mobile Number', 'Contact', ['Contact', 'PersonalInfo'], { mobile: '+61 4XX XXX 228', verified: 'Yes', preferredOtpChannel: 'App push' }),
    node('contact:mobile:push-channel', 'Push Channel', 'Evidence', ['Evidence', 'ContactDetail'], { channel: 'CommBank app push', preferred: 'Yes', smsFallback: 'Disabled for this action' }),
    node('contact:email', 'Email', 'Contact', ['Contact', 'PersonalInfo'], { email: 'jack.thompson@example.com', verified: 'Yes', statementDelivery: 'Digital' }),
    node('address:registered', 'Registered Address', 'Address', ['Address', 'PersonalInfo'], { address: 'Registered address on file', usage: 'Card fulfilment only', changeHold: 'No new address accepted during card replacement' }),
    node('device:iphone', 'Trusted iPhone', 'Device', ['Device', 'Security'], { device: 'iPhone 15 Pro', appVersion: '5.34.1', lastSeen: 'Today 10:14 AEST', trustScore: 'Strong' }),
    node('device:iphone:trust-score', 'Device Trust Score', 'Evidence', ['Evidence', 'DeviceDetail'], { trustScore: 'Strong', deviceBinding: 'Stable', recentRisk: 'None' }),
    node('device:browser', 'Web Session', 'Device', ['Device', 'Session'], { channel: 'Web banking', ipRegion: 'NSW', lastLogin: 'Yesterday 21:06 AEST' }),
    node('profile:premier', 'Premier Relationship', 'Preference', ['Preference', 'Relationship'], { rm: 'Aria', contactStyle: 'Short conversational steps', sensitivity: 'Financial hardship and credit-record impact' }),
    node('account:everyday', 'Everyday Account', 'Account', ['Account'], { bsb: '062-000', maskedAccount: 'xxxx-0381', status: 'Open', balanceBand: 'Healthy' }),
    node('account:offset', 'Offset Account', 'Account', ['Account'], { maskedAccount: 'xxxx-7720', linkedLoan: 'Home loan HL-2041', status: 'Restricted by card freeze workflow' }),
    node('account:savings', 'GoalSaver', 'Account', ['Account'], { maskedAccount: 'xxxx-1199', status: 'Open', directDebits: 'None' }),
    node('card:visa4481', 'Awards Visa 4481', 'Card', ['Card'], { product: 'CommBank Awards Visa', lastFour: '4481', status: 'Temporarily frozen', reason: 'Unusual transaction sequence' }),
    node('card:visa4481:status', 'Freeze Status', 'Evidence', ['Evidence', 'CardDetail'], { status: 'Temporarily frozen', actionSource: 'Automated risk control', reversible: 'Yes' }),
    node('card:digital', 'Digital Card', 'Card', ['Card', 'Remediation'], { status: 'Ready to activate', walletSupport: 'Apple Pay, Google Pay', availability: 'Immediate after consent' }),
    node('card:digital:wallets', 'Wallet Rails', 'Evidence', ['Evidence', 'CardDetail'], { supportedWallets: 'Apple Pay, Google Pay', availability: 'Immediate', requiresConsent: 'Yes' }),
    node('fulfilment:physical-card', 'Physical Card Shipment', 'Remediation', ['Remediation', 'Fulfilment'], { method: 'Express post', eta: '1-2 business days', destination: 'Registered address only' }),
    node('txn:electronics', 'Electronics Purchase', 'Transaction', ['Transaction'], { amount: '$1,842.77', merchant: 'Electronics retailer', timestamp: 'Today 09:42 AEST', customerConfirmed: 'Pending conversation' }),
    node('txn:electronics:merchant', 'Merchant Detail', 'Evidence', ['Evidence', 'TransactionDetail'], { merchant: 'Electronics retailer', category: 'Consumer electronics', amount: '$1,842.77' }),
    node('txn:fuel', 'Fuel Purchase', 'Transaction', ['Transaction'], { amount: '$92.18', timestamp: 'Today 08:17 AEST', pattern: 'Normal commute region' }),
    node('txn:coffee', 'Cafe Purchase', 'Transaction', ['Transaction'], { amount: '$6.40', timestamp: 'Today 07:54 AEST', pattern: 'Known merchant' }),
    node('risk:freeze', 'Freeze Decision', 'RiskSignal', ['RiskSignal'], { model: 'Card anomaly monitor', confidence: '83%', action: 'Temporary freeze', customerImpact: 'Linked payment disruption' }),
    node('risk:freeze:reason', 'Freeze Reason', 'Evidence', ['Evidence', 'RiskDetail'], { reason: 'Merchant anomaly + purchase size', modelConfidence: '83%', humanReview: 'Not required if customer confirms' }),
    node('risk:fraud-case', 'Fraud Review', 'RiskSignal', ['RiskSignal', 'Case'], { status: 'Not escalated', reason: 'Customer confirmation can resolve', sla: 'Same call' }),
    node('loan:home', 'Home Loan', 'Loan', ['Loan'], { loanId: 'HL-2041', repaymentFrequency: 'Monthly', repaymentSource: 'Offset account', hardshipFlag: 'No' }),
    node('payment:home-loan', 'Home Loan Payment', 'Payment', ['Payment'], { scheduledAmount: '$4,280.00', status: 'Rejected', rejectionReason: 'Linked account restriction', recordImpact: 'Avoidable with grace period' }),
    node('payment:home-loan:record-impact', 'Record Impact', 'Evidence', ['Evidence', 'PaymentDetail'], { impact: 'Preventable', condition: 'Grace period applied within 14 days', reportingStatus: 'No record impact yet' }),
    node('payment:insurance', 'Insurance Premium', 'Payment', ['Payment'], { scheduledAmount: '$146.20', status: 'Unaffected', nextRun: '2026-06-03' }),
    node('case:incident', 'Premier Care Case', 'Case', ['Case'], { caseType: 'Card freeze flow-on impact', priority: 'Premier', owner: 'Aria', nextBestAction: 'Verify, confirm purchase, offer grace period' }),
    node('remediation:grace', 'Grace Period', 'Remediation', ['Remediation'], { status: 'Available after consent', duration: '14 days', creditRecordImpact: 'None when applied in window' }),
    node('remediation:grace:expiry', 'Grace Expiry', 'Evidence', ['Evidence', 'RemediationDetail'], { duration: '14 days', expiry: '14 days from today', recordImpact: 'None in window' }),
    node('consent:grace', 'Grace Consent', 'Consent', ['Consent'], { required: 'Yes', capture: 'Voice confirmation', state: 'Not yet captured' }),
    node('consent:digital-card', 'Digital Card Consent', 'Consent', ['Consent'], { required: 'Yes', capture: 'Voice confirmation', state: 'Not yet captured' }),
    node('employer:firm', 'Employer Payroll', 'Employer', ['Employer'], { employer: 'Private professional services firm', salaryCredits: 'Regular', relevance: 'Affordability context only; no credit decision' }),
    node('preference:wallet', 'Wallet Preference', 'Preference', ['Preference'], { preferredWallet: 'Apple Pay', previousDigitalUse: 'Frequent', cardReplacementFit: 'High' })
  ];

  const links = [
    link('customer:jack', 'identity:biometric', 'VERIFIED_BY', { recency: 'current call', confidence: '99.6%' }),
    link('identity:biometric', 'identity:biometric:confidence', 'HAS_DETAIL', { field: 'confidence' }),
    link('identity:biometric:confidence', 'identity:biometric:timestamp', 'VALIDATED_AT', { field: 'timestamp' }),
    link('identity:biometric', 'identity:kyc', 'UNLOCKS_PROFILE', { reason: 'verification complete' }),
    link('identity:kyc', 'identity:passport', 'MATCHES_DOCUMENT', { verification: 'file match' }),
    link('identity:passport', 'contact:mobile', 'SUPPORTS_CONTACT', { status: 'trusted' }),
    link('contact:mobile', 'contact:mobile:push-channel', 'USES_CHANNEL', { preferred: 'true' }),
    link('contact:mobile', 'contact:email', 'BELONGS_TO_CUSTOMER', { verified: 'true' }),
    link('contact:email', 'device:iphone', 'BOUND_TO_DEVICE', { appInstall: 'current' }),
    link('device:iphone', 'device:iphone:trust-score', 'HAS_TRUST_SCORE', { result: 'strong' }),
    link('device:iphone', 'address:registered', 'CONFIRMS_PROFILE', { trustScore: 'strong' }),
    link('address:registered', 'profile:premier', 'REGISTERED_FOR', { fulfilmentLocked: 'true' }),
    link('profile:premier', 'card:visa4481', 'PRIORITISES_CARD_CASE', { tier: 'Premier' }),
    link('card:visa4481', 'card:visa4481:status', 'HAS_STATUS', { status: 'frozen' }),
    link('card:visa4481', 'txn:electronics', 'AUTHORISED_TRANSACTION', { amount: '$1,842.77' }),
    link('txn:electronics', 'txn:electronics:merchant', 'HAS_MERCHANT_DETAIL', { merchantCategory: 'electronics' }),
    link('txn:electronics', 'risk:freeze', 'TRIGGERED_SIGNAL', { signal: 'velocity + merchant anomaly' }),
    link('risk:freeze', 'risk:freeze:reason', 'HAS_REASON', { reason: 'merchant anomaly' }),
    link('risk:freeze', 'risk:fraud-case', 'OPENED_REVIEW', { severity: 'medium' }),
    link('risk:fraud-case', 'account:offset', 'IMPACTS_LINKED_ACCOUNT', { flowOnImpact: 'true' }),
    link('account:offset', 'loan:home', 'OFFSETS_LOAN', { loanId: 'HL-2041' }),
    link('loan:home', 'payment:home-loan', 'HAS_REPAYMENT', { frequency: 'monthly' }),
    link('payment:home-loan', 'payment:home-loan:record-impact', 'HAS_IMPACT_STATUS', { status: 'preventable' }),
    link('payment:home-loan', 'case:incident', 'CREATED_CASE', { priority: 'Premier' }),
    link('case:incident', 'consent:grace', 'REQUIRES_CONSENT', { channel: 'voice' }),
    link('consent:grace', 'remediation:grace', 'ENABLES', { duration: '14 days' }),
    link('remediation:grace', 'remediation:grace:expiry', 'HAS_EXPIRY', { duration: '14 days' }),
    link('remediation:grace', 'consent:digital-card', 'NEXT_ACTION', { digitalFirst: 'true' }),
    link('consent:digital-card', 'card:digital', 'ENABLES_ACTIVATION', { walletSupport: 'Apple Pay, Google Pay' }),
    link('card:digital', 'card:digital:wallets', 'HAS_WALLET_RAILS', { wallets: 'Apple Pay, Google Pay' }),
    link('card:digital', 'fulfilment:physical-card', 'PAIRS_WITH_SHIPMENT', { eta: '1-2 business days' }),
    link('card:visa4481', 'txn:fuel', 'AUTHORISED_TRANSACTION', { amount: '$92.18' }),
    link('card:visa4481', 'txn:coffee', 'AUTHORISED_TRANSACTION', { amount: '$6.40' }),
    link('customer:jack', 'account:everyday', 'OWNS_ACCOUNT', { role: 'primary' }),
    link('customer:jack', 'account:savings', 'OWNS_ACCOUNT', { role: 'savings' }),
    link('account:everyday', 'payment:insurance', 'FUNDS_PAYMENT', { status: 'unaffected' }),
    link('fulfilment:physical-card', 'address:registered', 'SHIPS_ONLY_TO', { guardrail: 'registered address only' }),
    link('customer:jack', 'employer:firm', 'RECEIVES_SALARY_FROM', { creditDecisionUse: 'prohibited in this call' }),
    link('card:digital', 'preference:wallet', 'MATCHES_PREFERENCE', { fit: 'high' })
  ];

  for (let i = 1; i <= 12; i += 1) {
    const label = ['Transaction', 'RiskSignal', 'Preference', 'Contact', 'Device', 'Account'][i % 6];
    const id = `context:signal-${i}`;
    nodes.push(node(id, `Context Signal ${i}`, label, [label, 'Context'], {
      source: ['Cards', 'Payments', 'Digital', 'CRM', 'Fraud', 'Premier'][i % 6],
      confidence: `${66 + (i % 31)}%`,
      relevance: ['Supports verification', 'Explains impact', 'Shapes next best action', 'Confirms guardrail'][i % 4]
    }));
    links.push(link('case:incident', id, 'CONSIDERS_SIGNAL', { rank: String(i) }));
  }

  return { nodes, links };
}

function node(id, label, primaryLabel, labels, properties) {
  return { id, label, primaryLabel, labels, properties };
}

function link(source, target, type, properties) {
  return { source, target, type, properties };
}
