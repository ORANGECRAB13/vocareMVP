// App root — Georges River Council Dashboard

const { useState, useEffect } = React;

function App() {
  const [page, setPage] = useState(() => localStorage.getItem('grc-page') || 'dashboard');
  const [sidebarStyle, setSidebarStyle] = useState('light');

  useEffect(() => {
    localStorage.setItem('grc-page', page);
  }, [page]);

  useEffect(() => {
    const handler = e => {
      if (e.detail?.sidebar) setSidebarStyle(e.detail.sidebar);
    };
    window.addEventListener('tweaks-changed', handler);
    return () => window.removeEventListener('tweaks-changed', handler);
  }, []);

  const navigate = p => setPage(p);

  const renderPage = () => {
    switch (page) {
      case 'dashboard':  return <GRCDashboard onNavigate={navigate} />;
      case 'live-calls': return <LiveCallsPage onTakeover={() => {}} />;
      case 'agents':     return <AgentsPage />;
      case 'history':    return <HistoryPage />;
      default:           return <GRCDashboard onNavigate={navigate} />;
    }
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar activePage={page} onNavigate={navigate} style={sidebarStyle} />
      <div style={{ marginLeft: 240, flex: 1, display: 'flex', flexDirection: 'column' }}>
        <Header activePage={page} />
        <main style={{ flex: 1, overflowY: 'auto', paddingTop: 64 }}>
          {renderPage()}
        </main>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
