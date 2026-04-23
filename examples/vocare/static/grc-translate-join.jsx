const { useState, useEffect, useRef } = React;

function TranslateJoinPage({ sessionId }) {
  const [sessionInfo, setSessionInfo] = useState(null);
  const [name, setName] = useState('');
  const [language, setLanguage] = useState('en');
  const [status, setStatus] = useState('joining'); // joining, connecting, connected, error
  const [errorMsg, setErrorMsg] = useState('');
  const [isTalking, setIsTalking] = useState(false);

  const pcRef = useRef(null);
  const audioRef = useRef(null);
  const localStreamRef = useRef(null);

  useEffect(() => {
    fetch(`/api/translation/session/${sessionId}`)
      .then(res => {
        if (!res.ok) throw new Error("Session not found");
        return res.json();
      })
      .then(data => setSessionInfo(data))
      .catch(() => {
        setStatus('error');
        setErrorMsg('Session not found or has ended.');
      });
  }, [sessionId]);

  const handleJoin = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setStatus('connecting');

    try {
      // 1. Get microphone — start muted for PTT
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getAudioTracks().forEach(track => track.enabled = false);
      localStreamRef.current = stream;

      // 2. Fetch ICE servers
      const iceRes = await fetch('/api/ice');
      const iceData = await iceRes.json();

      // 3. Create WebRTC peer connection
      const pc = new RTCPeerConnection({ iceServers: iceData.iceServers });
      pcRef.current = pc;

      // When the server sends translated audio back, play it
      pc.ontrack = (evt) => {
        if (audioRef.current && evt.streams[0]) {
          audioRef.current.srcObject = evt.streams[0];
          audioRef.current.play().catch(() => {});
        }
      };

      stream.getTracks().forEach(track => pc.addTrack(track, stream));

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      // 4. CRITICAL: wait for ICE gathering to finish before sending the offer.
      //    If we send early the SDP contains no candidates and the server
      //    can never establish a connection back → timeout.
      await new Promise((resolve) => {
        if (pc.iceGatheringState === 'complete') {
          resolve();
        } else {
          const onStateChange = () => {
            if (pc.iceGatheringState === 'complete') {
              pc.removeEventListener('icegatheringstatechange', onStateChange);
              resolve();
            }
          };
          pc.addEventListener('icegatheringstatechange', onStateChange);
          setTimeout(resolve, 5000); // safety: never wait more than 5s
        }
      });

      // 5. Send offer (now with full ICE candidates) to backend
      const offerRes = await fetch('/api/translation/offer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          name: name,
          language: language,
          sdp: pc.localDescription.sdp,
          type: pc.localDescription.type,
        }),
      });

      if (!offerRes.ok) throw new Error(await offerRes.text());

      const answer = await offerRes.json();
      await pc.setRemoteDescription(answer);

      setStatus('connected');
    } catch (err) {
      console.error(err);
      setStatus('error');
      setErrorMsg(err.message || 'Failed to connect');
    }
  };

  const handleStartTalk = () => {
    setIsTalking(true);
    localStreamRef.current?.getAudioTracks().forEach(t => t.enabled = true);
  };

  const handleStopTalk = () => {
    setIsTalking(false);
    localStreamRef.current?.getAudioTracks().forEach(t => t.enabled = false);
  };

  if (status === 'error') {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#F4F5F6' }}>
        <div style={{ background: '#fff', padding: 32, borderRadius: 16, textAlign: 'center', border: '1px solid #E8E9EB' }}>
          <span className="material-symbols-outlined" style={{ fontSize: 48, color: 'var(--grc-red)', display: 'block', marginBottom: 16 }}>error</span>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>Error joining session</h1>
          <p style={{ color: '#666', marginBottom: 20 }}>{errorMsg}</p>
          <button onClick={() => window.location.reload()} style={{ padding: '10px 24px', background: 'var(--grc-teal)', color: '#fff', borderRadius: 8, fontWeight: 600 }}>Try Again</button>
        </div>
      </div>
    );
  }

  if (status === 'connected') {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#F4F5F6', userSelect: 'none' }}>
        <div style={{ background: '#fff', padding: 48, borderRadius: 16, textAlign: 'center', border: '1px solid #E8E9EB', width: 420 }}>
          <div style={{
            width: 80, height: 80, borderRadius: '50%',
            background: isTalking ? 'var(--grc-teal)' : 'var(--grc-teal-light)',
            color: isTalking ? '#fff' : 'var(--grc-teal-dark)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 24px', transition: 'all 0.2s',
            transform: isTalking ? 'scale(1.15)' : 'scale(1)',
          }}>
            <span className="material-symbols-outlined" style={{ fontSize: 40 }}>{isTalking ? 'mic' : 'mic_off'}</span>
          </div>

          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 6 }}>Connected</h1>
          <p style={{ color: '#666', marginBottom: 4 }}>{sessionInfo?.topic}</p>
          <p style={{ color: '#aaa', fontSize: 13, marginBottom: 28 }}>
            Speaking as <strong>{name}</strong> · {language === 'en' ? '🇦🇺 English' : '🇨🇳 Mandarin'}
          </p>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, marginBottom: 28 }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: isTalking ? 'var(--grc-teal)' : '#ccc', transition: 'background 0.2s' }} />
            <span style={{ fontSize: 14, fontWeight: 600, color: isTalking ? 'var(--grc-teal)' : '#888' }}>
              {isTalking ? 'Transmitting...' : 'Muted — hold to speak'}
            </span>
          </div>

          <button
            onMouseDown={handleStartTalk}
            onMouseUp={handleStopTalk}
            onMouseLeave={handleStopTalk}
            onTouchStart={(e) => { e.preventDefault(); handleStartTalk(); }}
            onTouchEnd={(e) => { e.preventDefault(); handleStopTalk(); }}
            style={{
              padding: '18px 32px',
              background: isTalking ? 'var(--grc-teal-dark)' : 'var(--grc-teal)',
              color: '#fff', borderRadius: 10, fontWeight: 700, fontSize: 16,
              width: '100%', marginBottom: 14,
              boxShadow: isTalking ? 'inset 0 4px 8px rgba(0,0,0,0.2)' : '0 4px 16px rgba(0,169,165,0.35)',
              transform: isTalking ? 'translateY(2px) scale(0.99)' : 'none',
              transition: 'all 0.1s', touchAction: 'none',
            }}
          >
            {isTalking ? '🎙 Release to Mute' : '🎤 Hold to Speak'}
          </button>

          <button
            onClick={() => window.location.reload()}
            style={{ padding: '10px 24px', background: 'transparent', color: 'var(--grc-red)', border: '1px solid var(--grc-red)', borderRadius: 8, fontWeight: 600, width: '100%' }}
          >
            Leave Session
          </button>

          {/* Hidden audio element that plays translated speech from the other participant */}
          <audio ref={audioRef} autoPlay playsInline style={{ display: 'none' }} />
        </div>
      </div>
    );
  }

  // Joining / connecting form
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#F4F5F6' }}>
      <div style={{ background: '#fff', padding: 40, borderRadius: 16, border: '1px solid #E8E9EB', width: 420 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 6 }}>Join Translation Session</h1>
        <p style={{ color: '#666', marginBottom: 28 }}>{sessionInfo ? `Topic: ${sessionInfo.topic}` : 'Loading session...'}</p>

        <form onSubmit={handleJoin} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Your Name</label>
            <input
              type="text" required placeholder="Enter your name"
              value={name} onChange={e => setName(e.target.value)}
              style={{ width: '100%', padding: '12px 16px', border: '1px solid #ddd', borderRadius: 8, fontSize: 15 }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Your Spoken Language</label>
            <select
              value={language} onChange={e => setLanguage(e.target.value)}
              style={{ width: '100%', padding: '12px 16px', border: '1px solid #ddd', borderRadius: 8, fontSize: 15 }}
            >
              <option value="en">🇦🇺 English</option>
              <option value="zh">🇨🇳 Mandarin</option>
            </select>
          </div>
          <button
            type="submit"
            disabled={!sessionInfo || status !== 'joining'}
            style={{
              padding: '14px', background: 'var(--grc-teal)', color: '#fff',
              borderRadius: 8, fontWeight: 700, fontSize: 15, marginTop: 8,
              opacity: (!sessionInfo || status !== 'joining') ? 0.6 : 1,
              cursor: (!sessionInfo || status !== 'joining') ? 'not-allowed' : 'pointer',
            }}
          >
            {status === 'connecting' ? '⏳ Gathering connection info...' : 'Join Session'}
          </button>
        </form>
      </div>
    </div>
  );
}

Object.assign(window, { TranslateJoinPage });
