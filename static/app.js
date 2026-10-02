let state = {
  accounts: [],
  activeIdeAccountId: null,
  config: {},
  rotations: [],
  currentFilter: 'all',
  integrations: null
};

function showToast(msg, isError = false) {
  const toast = document.getElementById('toast');
  const toastMsg = document.getElementById('toast-msg');
  const toastIcon = document.getElementById('toast-icon');

  toastMsg.innerText = msg;
  if (isError) {
    toastIcon.className = 'fa-solid fa-circle-exclamation text-rose-400 text-base';
  } else {
    toastIcon.className = 'fa-solid fa-circle-check text-emerald-400 text-base';
  }

  toast.classList.remove('translate-y-[-20px]', 'opacity-0', 'pointer-events-none');
  setTimeout(() => {
    toast.classList.add('translate-y-[-20px]', 'opacity-0', 'pointer-events-none');
  }, 4000);
}

// Check URL query parameters for OAuth status
window.addEventListener('DOMContentLoaded', () => {
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('oauth_success')) {
    showToast('Đăng nhập Google thành công! Tài khoản đã được thêm vào pool.');
    window.history.replaceState({}, document.title, window.location.pathname);
  } else if (urlParams.get('oauth_error')) {
    showToast('Lỗi đăng nhập Google: ' + urlParams.get('oauth_error'), true);
    window.history.replaceState({}, document.title, window.location.pathname);
  }

  // Load initial data and check integration status
  loadData();
  checkIntegrations();
  setInterval(loadData, 5000);
});

// Tab Switching Navigation
function switchTab(tabId) {
  const tabs = ['dashboard', 'integrations', 'rotations', 'settings'];
  tabs.forEach(tab => {
    const tabEl = document.getElementById(`tab-${tab}`);
    const btnEl = document.getElementById(`tab-btn-${tab}`);
    if (!tabEl || !btnEl) return;

    if (tab === tabId) {
      tabEl.classList.remove('hidden');
      btnEl.classList.add('active');
      btnEl.classList.remove('text-slate-400', 'border-transparent');
    } else {
      tabEl.classList.add('hidden');
      btnEl.classList.remove('active');
      btnEl.classList.add('text-slate-400', 'border-transparent');
    }
  });

  if (tabId === 'integrations') {
    checkIntegrations();
  }
}

// Account Filtering
function filterAccounts(type) {
  state.currentFilter = type;
  const pillIds = ['filter-all', 'filter-pro', 'filter-free', 'filter-ready'];
  pillIds.forEach(id => {
    const btn = document.getElementById(id);
    if (!btn) return;
    if (id === `filter-${type}`) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
  renderAccounts();
}

async function loadData() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    state.accounts = data.accounts || [];
    state.activeIdeAccountId = data.active_ide_account_id;
    state.currentApiAccountId = data.current_api_account_id || data.active_ide_account_id;
    state.config = data.config || {};
    state.rotations = data.rotations || [];

    renderStats();
    renderAccounts();
    renderRotations();
  } catch (err) {
    console.error('Failed to load status:', err);
  }
}

function renderStats() {
  const total = state.accounts.length;
  const proCount = state.accounts.filter(a => a.plan_type === 'PRO').length;
  const freeCount = total - proCount;

  document.getElementById('stat-total-accounts').innerText = total;
  document.getElementById('stat-pro-accounts').innerText = proCount;
  document.getElementById('stat-free-accounts').innerText = freeCount;
  document.getElementById('count-all').innerText = total;
  document.getElementById('count-pro').innerText = proCount;
  document.getElementById('count-free').innerText = freeCount;

  document.getElementById('stat-strategy').innerText = state.config.rotation_strategy || 'Highest Quota';
  document.getElementById('stat-threshold').innerText = Math.round((state.config.min_quota_threshold || 0.05) * 100) + '%';
  document.getElementById('stat-total-rotations').innerText = state.rotations.length;

  // Active Account
  const activeAcc = state.accounts.find(a => a.id === (state.activeIdeAccountId || state.currentApiAccountId)) || (state.accounts.length > 0 ? state.accounts[0] : null);

  if (activeAcc) {
    const isPro = activeAcc.plan_type === 'PRO';
    document.getElementById('stat-active-ide').innerHTML = `
      <div class="flex items-center space-x-1.5 truncate">
        ${isPro ? '<i class="fa-solid fa-crown text-amber-400 text-xs"></i>' : '<i class="fa-solid fa-circle-check text-emerald-400 text-xs"></i>'}
        <span class="truncate font-semibold">${activeAcc.email}</span>
      </div>
    `;
  } else {
    document.getElementById('stat-active-ide').innerText = 'Chưa đồng bộ';
  }

  // Render standout Active Account Banner
  const banner = document.getElementById('active-account-banner');
  if (banner) {
    if (activeAcc) {
      banner.classList.remove('hidden');
      const isPro = activeAcc.plan_type === 'PRO';
      const initials = (activeAcc.email || 'AG').substring(0, 2).toUpperCase();
      const initialsEl = document.getElementById('active-acc-initials');
      if (initialsEl) initialsEl.innerText = initials;

      const crownEl = document.getElementById('active-acc-crown');
      if (crownEl) {
        if (isPro) crownEl.classList.remove('hidden');
        else crownEl.classList.add('hidden');
      }

      const emailEl = document.getElementById('active-acc-email');
      if (emailEl) emailEl.innerText = activeAcc.email;
      const nameEl = document.getElementById('active-acc-name');
      if (nameEl) nameEl.innerText = activeAcc.name ? `(${activeAcc.name})` : '';

      const badgeEl = document.getElementById('active-acc-tier-badge');
      if (badgeEl) {
        if (isPro) {
          badgeEl.className = 'px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/50 flex items-center gap-1';
          badgeEl.innerHTML = '<i class="fa-solid fa-crown text-[9px]"></i> 👑 PRO';
        } else {
          badgeEl.className = 'px-2 py-0.5 rounded text-[10px] font-bold bg-slate-800 text-slate-300 border border-slate-700';
          badgeEl.innerText = '🆓 BẢN THƯỜNG';
        }
      }

      const geminiWk = activeAcc.quota_buckets && activeAcc.quota_buckets['gemini-weekly'] ? activeAcc.quota_buckets['gemini-weekly'].remaining_fraction : 1.0;
      const gemini5h = activeAcc.quota_buckets && activeAcc.quota_buckets['gemini-5h'] ? activeAcc.quota_buckets['gemini-5h'].remaining_fraction : 1.0;
      const claudeWk = activeAcc.quota_buckets && activeAcc.quota_buckets['3p-weekly'] ? activeAcc.quota_buckets['3p-weekly'].remaining_fraction : 1.0;
      const claude5h = activeAcc.quota_buckets && activeAcc.quota_buckets['3p-5h'] ? activeAcc.quota_buckets['3p-5h'].remaining_fraction : 1.0;

      const gPct = Math.round(Math.min(geminiWk, gemini5h) * 100);
      const cPct = Math.round(Math.min(claudeWk, claude5h) * 100);

      const gEl = document.getElementById('active-acc-gemini-pct');
      if (gEl) gEl.innerText = `${gPct}%`;
      const gBar = document.getElementById('active-acc-gemini-bar');
      if (gBar) {
        gBar.style.width = `${gPct}%`;
        gBar.className = (gPct > 50 ? 'bg-emerald-500' : (gPct > 20 ? 'bg-amber-500' : 'bg-rose-500')) + ' h-full rounded-full transition-all duration-500';
      }

      const cEl = document.getElementById('active-acc-claude-pct');
      if (cEl) cEl.innerText = `${cPct}%`;
      const cBar = document.getElementById('active-acc-claude-bar');
      if (cBar) {
        cBar.style.width = `${cPct}%`;
        cBar.className = (cPct > 50 ? 'bg-emerald-500' : (cPct > 20 ? 'bg-amber-500' : 'bg-rose-500')) + ' h-full rounded-full transition-all duration-500';
      }
    } else {
      banner.classList.add('hidden');
    }
  }

  // Populate config fields in settings if not currently focused
  const refreshSelect = document.getElementById('cfg-auto-refresh');
  if (refreshSelect && state.config.auto_refresh_quota_interval !== undefined && document.activeElement !== refreshSelect) {
    refreshSelect.value = state.config.auto_refresh_quota_interval;
  }
  const stratSelect = document.getElementById('cfg-strategy');
  if (stratSelect && state.config.rotation_strategy && document.activeElement !== stratSelect) {
    stratSelect.value = state.config.rotation_strategy;
  }
  const threshInput = document.getElementById('cfg-threshold');
  if (threshInput && state.config.min_quota_threshold !== undefined && document.activeElement !== threshInput) {
    threshInput.value = Math.round(state.config.min_quota_threshold * 100);
  }
  const coolInput = document.getElementById('cfg-cooldown');
  if (coolInput && state.config.cooldown_seconds_on_429 !== undefined && document.activeElement !== coolInput) {
    coolInput.value = state.config.cooldown_seconds_on_429;
  }
  const apiInput = document.getElementById('cfg-apikey');
  if (apiInput && state.config.api_key !== undefined && document.activeElement !== apiInput) {
    apiInput.value = state.config.api_key || '';
  }
  const relaunchCheck = document.getElementById('cfg-auto-relaunch');
  if (relaunchCheck && state.config.auto_relaunch_antigravity !== undefined && document.activeElement !== relaunchCheck) {
    relaunchCheck.checked = Boolean(state.config.auto_relaunch_antigravity);
  }

  const port = state.config.port || 8088;
  const gwPort = document.getElementById('gateway-port');
  if (gwPort) gwPort.innerText = port;
  
  const openaiEl = document.getElementById('openai-endpoint-url');
  if (openaiEl) openaiEl.innerText = `http://127.0.0.1:${port}/v1`;

  const anthropicEl = document.getElementById('anthropic-endpoint-url');
  if (anthropicEl) anthropicEl.innerText = `http://127.0.0.1:${port}`;

  const cursorEl = document.getElementById('copy-cursor-url');
  if (cursorEl) cursorEl.innerText = `http://127.0.0.1:${port}/v1`;
}

function renderAccounts() {
  const container = document.getElementById('accounts-grid');
  if (!state.accounts.length) {
    container.innerHTML = `
      <div class="col-span-full py-12 text-center bg-slate-900 border border-slate-800 rounded-2xl p-6">
        <i class="fa-solid fa-folder-open text-slate-600 text-4xl mb-3"></i>
        <p class="text-slate-400 text-sm">Chưa có tài khoản nào trong hệ thống.</p>
        <button onclick="autoDiscoverAccounts()" class="mt-4 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-medium">
          Tự động tìm tài khoản trên máy
        </button>
      </div>
    `;
    return;
  }

  const now = Date.now() / 1000;

  // Filter accounts
  let filtered = state.accounts;
  if (state.currentFilter === 'pro') {
    filtered = state.accounts.filter(a => a.plan_type === 'PRO');
  } else if (state.currentFilter === 'free') {
    filtered = state.accounts.filter(a => a.plan_type !== 'PRO');
  } else if (state.currentFilter === 'ready') {
    filtered = state.accounts.filter(a => !a.disabled && (a.cooldown_until <= now));
  }

  if (!filtered.length) {
    container.innerHTML = `
      <div class="col-span-full py-10 text-center bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6">
        <i class="fa-solid fa-filter text-slate-600 text-3xl mb-2"></i>
        <p class="text-slate-400 text-xs">Không tìm thấy tài khoản nào khớp với bộ lọc "${state.currentFilter.toUpperCase()}".</p>
        <button onclick="filterAccounts('all')" class="mt-3 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs">
          Xem tất cả tài khoản
        </button>
      </div>
    `;
    return;
  }

  const currentActiveId = state.activeIdeAccountId || state.currentApiAccountId || (state.accounts[0] ? state.accounts[0].id : null);

  container.innerHTML = filtered.map(acc => {
    const isCurrentActive = acc.id === currentActiveId;
    const isCooldown = acc.cooldown_until > now;
    const isPro = acc.plan_type === 'PRO';

    let statusBadge = '';
    if (acc.disabled) {
      statusBadge = '<span class="px-2 py-0.5 rounded text-[11px] font-medium bg-red-950 text-red-400 border border-red-800">Đã tắt</span>';
    } else if (isCooldown) {
      const waitMins = Math.ceil((acc.cooldown_until - now) / 60);
      statusBadge = `<span class="px-2 py-0.5 rounded text-[11px] font-medium bg-amber-950 text-amber-400 border border-amber-800 cursor-pointer" onclick="resetCooldown('${acc.id}')" title="Nhấp để xóa Cooldown ngay">Cooldown (${waitMins}p) ✕</span>`;
    } else {
      statusBadge = '<span class="px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-950 text-emerald-400 border border-emerald-800">Sẵn sàng</span>';
    }

    const geminiWk = acc.quota_buckets && acc.quota_buckets['gemini-weekly'] ? acc.quota_buckets['gemini-weekly'].remaining_fraction : 1.0;
    const gemini5h = acc.quota_buckets && acc.quota_buckets['gemini-5h'] ? acc.quota_buckets['gemini-5h'].remaining_fraction : 1.0;
    const claudeWk = acc.quota_buckets && acc.quota_buckets['3p-weekly'] ? acc.quota_buckets['3p-weekly'].remaining_fraction : 1.0;
    const claude5h = acc.quota_buckets && acc.quota_buckets['3p-5h'] ? acc.quota_buckets['3p-5h'].remaining_fraction : 1.0;

    const geminiPct = Math.round(Math.min(geminiWk, gemini5h) * 100);
    const claudePct = Math.round(Math.min(claudeWk, claude5h) * 100);

    const getBarColor = (pct) => {
      if (pct > 50) return isPro ? 'bg-gradient-to-r from-amber-500 to-emerald-400' : 'bg-emerald-500';
      if (pct > 20) return 'bg-amber-500';
      return 'bg-rose-500';
    };

    return `
      <div class="account-card ${isPro ? 'is-pro' : ''} bg-slate-900 border ${isCurrentActive ? 'border-2 border-emerald-500 shadow-xl shadow-emerald-500/20 ring-1 ring-emerald-500/50 bg-gradient-to-b from-slate-900 via-slate-900 to-emerald-950/25' : (isPro ? 'border-amber-500/40' : 'border-slate-800')} rounded-2xl p-5 space-y-4 flex flex-col justify-between relative">
        ${isCurrentActive ? `
          <div class="absolute -top-3 left-5 px-3 py-0.5 rounded-full text-[10px] font-extrabold bg-emerald-500 text-slate-950 shadow-md flex items-center gap-1.5 uppercase tracking-wider">
            <i class="fa-solid fa-star"></i> ĐANG SỬ DỤNG HIỆN TẠI
          </div>
        ` : ''}

        <div>
          <!-- Header -->
          <div class="flex items-start justify-between ${isCurrentActive ? 'pt-1' : ''}">
            <div class="flex items-center space-x-3">
              ${isPro ? `
                <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500/20 to-orange-500/30 border border-amber-500/50 flex items-center justify-center font-bold text-amber-400 text-sm shadow-sm relative">
                  ${acc.email.substring(0, 2).toUpperCase()}
                  <span class="absolute -top-1.5 -right-1.5 text-amber-400 text-xs drop-shadow"><i class="fa-solid fa-crown"></i></span>
                </div>
              ` : `
                <div class="w-10 h-10 rounded-xl ${isCurrentActive ? 'bg-emerald-950/80 border border-emerald-500/60 text-emerald-300' : 'bg-slate-800 border border-slate-700 text-sky-400'} flex items-center justify-center font-bold text-sm">
                  ${acc.email.substring(0, 2).toUpperCase()}
                </div>
              `}
              <div class="overflow-hidden">
                <div class="font-semibold text-sm text-white truncate max-w-[150px] flex items-center">
                  <span>${acc.name || acc.email.split('@')[0]}</span>
                  <button onclick="openEditAccountModal('${acc.id}')" class="ml-1.5 text-slate-500 hover:text-slate-300 text-xs" title="Chỉnh sửa"><i class="fa-solid fa-pen-to-square"></i></button>
                </div>
                <div class="text-xs text-slate-400 font-mono truncate max-w-[170px]" title="${acc.email}">${acc.email}</div>
              </div>
            </div>
            <div class="flex flex-col items-end space-y-1">
              ${statusBadge}
              ${isPro ? `
                <button onclick="togglePlanType('${acc.id}')" title="Nhấp để đổi sang Bản Thường" class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/50 hover:bg-amber-500/30 transition flex items-center gap-1 cursor-pointer">
                  <i class="fa-solid fa-crown text-[9px]"></i> PRO
                </button>
              ` : `
                <button onclick="togglePlanType('${acc.id}')" title="Nhấp để nâng cấp lên Pro" class="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-400 border border-slate-700 hover:text-amber-400 hover:border-amber-500/50 transition cursor-pointer">
                  BẢN THƯỜNG
                </button>
              `}
            </div>
          </div>

          <!-- Quota Meters -->
          <div class="mt-4 space-y-2.5">
            <div>
              <div class="flex justify-between text-xs text-slate-300 mb-1">
                <span>Gemini Quota (Pro/Flash)</span>
                <span class="font-bold ${isPro ? 'text-amber-300' : ''}">${geminiPct}%</span>
              </div>
              <div class="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                <div class="${getBarColor(geminiPct)} h-full rounded-full transition-all duration-500" style="width: ${geminiPct}%"></div>
              </div>
            </div>

            <div>
              <div class="flex justify-between text-xs text-slate-300 mb-1">
                <span>Claude Quota (Opus/Sonnet)</span>
                <span class="font-bold ${isPro ? 'text-amber-300' : ''}">${claudePct}%</span>
              </div>
              <div class="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                <div class="${getBarColor(claudePct)} h-full rounded-full transition-all duration-500" style="width: ${claudePct}%"></div>
              </div>
            </div>
          </div>

          <!-- Metadata -->
          <div class="mt-4 pt-3 border-t border-slate-800/80 grid grid-cols-2 gap-2 text-[11px] text-slate-400">
            <div>Tier: <span class="font-semibold ${isPro ? 'text-amber-300' : 'text-slate-200'}">${acc.tier_name || (isPro ? 'Google AI Pro' : 'Antigravity (Bản Thường)')}</span></div>
            <div>Priority: <span class="text-slate-200 font-semibold">${acc.priority}</span></div>
          </div>
        </div>

        <!-- Actions -->
        <div class="space-y-2 pt-2 border-t border-slate-800">
          ${isCurrentActive ? `
            <div class="w-full py-2 px-3 rounded-lg text-xs font-bold bg-emerald-600/25 text-emerald-300 border border-emerald-500/70 flex items-center justify-center space-x-1.5 shadow-sm">
              <i class="fa-solid fa-circle-check text-emerald-400"></i>
              <span>Đang Sử Dụng (Bản Thường & IDE)</span>
            </div>
          ` : `
            <button onclick="syncToIde('${acc.id}')" class="w-full py-2 px-3 rounded-lg text-xs font-medium bg-slate-800 hover:bg-sky-600/30 text-slate-200 hover:text-sky-200 border border-slate-700 hover:border-sky-500/60 transition flex items-center justify-center space-x-1.5 cursor-pointer">
              <i class="fa-solid fa-arrow-right-arrow-left text-sky-400"></i>
              <span>Chuyển Sang Dùng Tài Khoản Này</span>
            </button>
          `}
          
          <div class="grid grid-cols-3 gap-1.5 text-[11px]">
            <button onclick="refreshSingleQuota('${acc.id}')" class="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-center transition cursor-pointer" title="Làm mới Quota">
              <i class="fa-solid fa-rotate"></i> Quota
            </button>
            <button onclick="toggleAccount('${acc.id}')" class="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-center transition cursor-pointer">
              ${acc.disabled ? '<i class="fa-solid fa-play text-emerald-400"></i> Bật' : '<i class="fa-solid fa-pause text-amber-400"></i> Tắt'}
            </button>
            <button onclick="deleteAccount('${acc.id}')" class="p-1.5 bg-slate-800 hover:bg-rose-900/40 text-rose-400 rounded text-center transition cursor-pointer" title="Xóa tài khoản">
              <i class="fa-solid fa-trash"></i> Xóa
            </button>
          </div>
        </div>

      </div>
    `;
  }).join('');
}

function renderRotations() {
  const container = document.getElementById('rotation-log-container');
  if (!container) return;
  if (!state.rotations.length) {
    container.innerHTML = '<div class="p-8 text-center text-slate-500">Chưa có sự kiện xoay tài khoản nào. Sẵn sàng nhận yêu cầu!</div>';
    return;
  }

  container.innerHTML = state.rotations.map(r => `
    <div class="p-3.5 hover:bg-slate-800/40 flex items-center justify-between text-xs transition">
      <div class="flex items-center space-x-2">
        <span class="px-2 py-0.5 rounded text-[10px] bg-amber-950 text-amber-400 border border-amber-800">Auto-Rotate</span>
        <span class="text-slate-400 font-mono">${r.time_str}</span>
        <span class="text-slate-400">Model: <span class="text-sky-300 font-semibold">${r.model}</span></span>
        <span class="text-rose-400 font-semibold">${r.from_account}</span>
        <i class="fa-solid fa-arrow-right text-slate-500"></i>
        <span class="text-emerald-400 font-semibold">${r.to_account}</span>
      </div>
      <div class="text-[11px] text-slate-400 italic">${r.reason}</div>
    </div>
  `).join('');
}

// 1-Click Plan Type Toggle
async function togglePlanType(accId) {
  try {
    const res = await fetch(`/api/accounts/${accId}/toggle_plan`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(`Đã chuyển tài khoản sang ${data.plan_type === 'PRO' ? '👑 PRO' : '🆓 BẢN THƯỜNG'}!`);
      loadData();
    }
  } catch (err) {
    showToast('Lỗi đổi loại tài khoản: ' + err, true);
  }
}

// Integrations Status & Actions
async function checkIntegrations() {
  try {
    const res = await fetch('/api/integrations/status');
    const data = await res.json();
    state.integrations = data;

    const hermesBadge = document.getElementById('hermes-status-badge');
    if (hermesBadge) {
      if (data.hermes.connected) {
        hermesBadge.innerHTML = '<span class="px-2.5 py-1 rounded-full text-[11px] font-medium bg-emerald-950 text-emerald-400 border border-emerald-800 flex items-center gap-1"><i class="fa-solid fa-circle-check"></i> Đã kết nối Gateway</span>';
      } else if (data.hermes.installed) {
        hermesBadge.innerHTML = '<span class="px-2.5 py-1 rounded-full text-[11px] font-medium bg-sky-950 text-sky-400 border border-sky-800 flex items-center gap-1"><i class="fa-solid fa-circle-dot"></i> Đã cài đặt (Chưa kết nối)</span>';
      } else {
        hermesBadge.innerHTML = '<span class="px-2.5 py-1 rounded-full text-[11px] font-medium bg-slate-800 text-slate-400 border border-slate-700">Chưa cài đặt</span>';
      }
    }
  } catch (err) {
    console.error('Error checking integrations:', err);
  }
}

async function integrateHermes() {
  try {
    showToast('Đang kết nối Hermes Agent...');
    const res = await fetch('/api/integrations/hermes', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || 'Cấu hình Hermes Agent thành công!');
      checkIntegrations();
    } else {
      showToast(data.detail || 'Lỗi cấu hình Hermes', true);
    }
  } catch (err) {
    showToast('Lỗi: ' + err, true);
  }
}

async function integrateCodex() {
  try {
    showToast('Đang tạo shortcut Codex...');
    const res = await fetch('/api/integrations/codex', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || 'Đã tạo file chạy Codex ngoài Desktop!');
    } else {
      showToast(data.detail || 'Lỗi tạo shortcut Codex', true);
    }
  } catch (err) {
    showToast('Lỗi: ' + err, true);
  }
}

async function integrateClaudeCode() {
  try {
    showToast('Đang tạo shortcut Claude Code...');
    const res = await fetch('/api/integrations/claude_code', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || 'Đã tạo file chạy Claude Code!');
    } else {
      showToast(data.detail || 'Lỗi tạo file Claude Code', true);
    }
  } catch (err) {
    showToast('Lỗi: ' + err, true);
  }
}

async function restoreHermes() {
  if (!confirm('Khôi phục cấu hình mặc định ban đầu cho Hermes Agent?')) return;
  try {
    showToast('Đang khôi phục cấu hình mặc định Hermes...');
    const res = await fetch('/api/integrations/hermes/restore', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || 'Đã khôi phục Hermes thành công!');
      checkIntegrations();
    } else {
      showToast(data.detail || 'Lỗi khôi phục Hermes', true);
    }
  } catch (err) {
    showToast('Lỗi: ' + err, true);
  }
}

async function restoreCodex() {
  if (!confirm('Gỡ bỏ thiết lập API Hub cho Codex và quay về cấu hình OpenAI mặc định?')) return;
  try {
    showToast('Đang gỡ bỏ cấu hình API Hub cho Codex...');
    const res = await fetch('/api/integrations/codex/restore', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || 'Đã khôi phục Codex về mặc định!');
      checkIntegrations();
    } else {
      showToast(data.detail || 'Lỗi khôi phục Codex', true);
    }
  } catch (err) {
    showToast('Lỗi: ' + err, true);
  }
}

async function restoreClaudeCode() {
  if (!confirm('Gỡ bỏ thiết lập API Hub cho Claude Code và quay về cấu hình Anthropic mặc định?')) return;
  try {
    showToast('Đang gỡ bỏ cấu hình API Hub cho Claude Code...');
    const res = await fetch('/api/integrations/claude_code/restore', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || 'Đã khôi phục Claude Code về mặc định!');
      checkIntegrations();
    } else {
      showToast(data.detail || 'Lỗi khôi phục Claude Code', true);
    }
  } catch (err) {
    showToast('Lỗi: ' + err, true);
  }
}

async function refreshActiveAccountQuota() {
  const currentActiveId = state.activeIdeAccountId || state.currentApiAccountId || (state.accounts[0] ? state.accounts[0].id : null);
  if (!currentActiveId) {
    showToast('Chưa có tài khoản nào được kết nối!', true);
    return;
  }
  await refreshSingleQuota(currentActiveId);
}

async function startGoogleOAuth() {
  try {
    const res = await fetch('/api/oauth/login');
    const data = await res.json();
    if (data.auth_url) {
      window.open(data.auth_url, '_blank');
      closeAddAccountModal();
      showToast('Đã mở trang xác thực Google trên trình duyệt...');
    }
  } catch (err) {
    showToast('Lỗi mở OAuth: ' + err, true);
  }
}

async function syncToIde(accId) {
  try {
    const res = await fetch(`/api/accounts/${accId}/sync_ide`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      if (data.relaunched) {
        showToast('🚀 Đã hot-swap và đang tự động khởi động lại Antigravity để nạp token mới...');
      } else {
        showToast('Đã hot-swap tài khoản cho Antigravity! Bấm "Relaunch Antigravity" hoặc Ctrl+R để áp dụng ngay.');
      }
      loadData();
    } else {
      showToast('Lỗi đồng bộ: ' + data.error, true);
    }
  } catch (err) {
    showToast('Lỗi: ' + err, true);
  }
}

async function relaunchAntigravity() {
  if (!confirm('Khởi động lại Antigravity ngay bây giờ?\n(Toàn bộ tab, phiên chat và công việc hiện tại sẽ được tự động giữ nguyên và nạp lại với tài khoản mới)')) {
    return;
  }
  try {
    showToast('🚀 Đang gửi lệnh khởi động lại Antigravity...');
    const res = await fetch('/api/antigravity/relaunch', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast('🚀 Antigravity đang đóng và khởi động lại trong giây lát...');
    } else {
      showToast(data.detail || 'Lỗi khởi động lại', true);
    }
  } catch (err) {
    showToast('Lỗi: ' + err, true);
  }
}

async function resetCooldown(accId) {
  try {
    await fetch(`/api/accounts/${accId}/reset_cooldown`, { method: 'POST' });
    showToast('Đã mở khóa Cooldown cho tài khoản.');
    loadData();
  } catch (err) {
    showToast('Lỗi: ' + err, true);
  }
}

async function refreshSingleQuota(accId) {
  try {
    showToast('Đang kiểm tra Quota...');
    await fetch(`/api/accounts/${accId}/refresh_quota`, { method: 'POST' });
    showToast('Cập nhật Quota thành công!');
    loadData();
  } catch (err) {
    showToast('Lỗi: ' + err, true);
  }
}

async function refreshAllQuotas() {
  try {
    showToast('Đang cập nhật Quota toàn bộ tài khoản...');
    await fetch('/api/accounts/refresh_all_quotas', { method: 'POST' });
    showToast('Đã làm mới Quota cho tất cả tài khoản!');
    loadData();
  } catch (err) {
    showToast('Lỗi: ' + err, true);
  }
}

async function toggleAccount(accId) {
  try {
    await fetch(`/api/accounts/${accId}/toggle`, { method: 'POST' });
    loadData();
  } catch (err) {
    console.error(err);
  }
}

async function deleteAccount(accId) {
  if (!confirm('Bạn có chắc muốn xóa tài khoản này khỏi danh sách quản lý?')) return;
  try {
    await fetch(`/api/accounts/${accId}`, { method: 'DELETE' });
    showToast('Đã xóa tài khoản.');
    loadData();
  } catch (err) {
    showToast('Lỗi: ' + err, true);
  }
}

async function autoDiscoverAccounts() {
  try {
    const res = await fetch('/api/accounts/discover', { method: 'POST' });
    const data = await res.json();
    showToast(`Đã quét và nạp ${data.imported_count} tài khoản từ máy.`);
    loadData();
  } catch (err) {
    showToast('Lỗi quét: ' + err, true);
  }
}

function openAddAccountModal() {
  document.getElementById('add-account-modal').classList.remove('hidden');
}

function closeAddAccountModal() {
  document.getElementById('add-account-modal').classList.add('hidden');
}

async function submitAddAccount() {
  const email = document.getElementById('modal-email').value.trim();
  const name = document.getElementById('modal-name').value.trim();
  const rawToken = document.getElementById('modal-refresh-token').value.trim();
  const priority = parseInt(document.getElementById('modal-priority').value) || 50;
  const planType = document.getElementById('modal-plan-type').value || 'FREE';

  if (!email || !rawToken) {
    alert('Vui lòng nhập Email và Refresh Token (hoặc dùng Cách 1 Đăng nhập Trình duyệt)!');
    return;
  }

  let rfToken = rawToken;
  try {
    if (rawToken.startsWith('{')) {
      const parsed = JSON.parse(rawToken);
      rfToken = parsed.refresh_token || (parsed.token && parsed.token.refresh_token) || rfToken;
    }
  } catch (e) {}

  try {
    const res = await fetch('/api/accounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email,
        name: name,
        refresh_token: rfToken,
        priority: priority,
        plan_type: planType
      })
    });
    const data = await res.json();
    if (data.success) {
      closeAddAccountModal();
      showToast('Đã thêm tài khoản thành công!');
      loadData();
    } else {
      showToast('Lỗi: ' + data.error, true);
    }
  } catch (err) {
    showToast('Lỗi: ' + err, true);
  }
}

function openEditAccountModal(accId) {
  const acc = state.accounts.find(a => a.id === accId);
  if (!acc) return;
  document.getElementById('edit-acc-id').value = acc.id;
  document.getElementById('edit-acc-email').value = acc.email;
  document.getElementById('edit-acc-name').value = acc.name || '';
  document.getElementById('edit-acc-priority').value = acc.priority || 50;
  document.getElementById('edit-acc-plan').value = acc.plan_type || 'FREE';
  document.getElementById('edit-account-modal').classList.remove('hidden');
}

function closeEditAccountModal() {
  document.getElementById('edit-account-modal').classList.add('hidden');
}

async function submitEditAccount() {
  const id = document.getElementById('edit-acc-id').value;
  const name = document.getElementById('edit-acc-name').value.trim();
  const priority = parseInt(document.getElementById('edit-acc-priority').value) || 50;
  const plan_type = document.getElementById('edit-acc-plan').value;

  try {
    await fetch(`/api/accounts/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, priority, plan_type })
    });
    closeEditAccountModal();
    showToast('Đã cập nhật thông tin tài khoản!');
    loadData();
  } catch (err) {
    showToast('Lỗi: ' + err, true);
  }
}

function openConfigModal() {
  document.getElementById('cfg-strategy').value = state.config.rotation_strategy || 'highest_quota';
  document.getElementById('cfg-threshold').value = Math.round((state.config.min_quota_threshold || 0.05) * 100);
  document.getElementById('cfg-cooldown').value = state.config.cooldown_seconds_on_429 || 900;
  const autoRefreshEl = document.getElementById('cfg-auto-refresh');
  if (autoRefreshEl && state.config.auto_refresh_quota_interval !== undefined) {
    autoRefreshEl.value = state.config.auto_refresh_quota_interval;
  }
  const autoRelaunchEl = document.getElementById('cfg-auto-relaunch');
  if (autoRelaunchEl && state.config.auto_relaunch_antigravity !== undefined) {
    autoRelaunchEl.checked = Boolean(state.config.auto_relaunch_antigravity);
  }
  document.getElementById('cfg-apikey').value = state.config.api_key || '';
  document.getElementById('config-modal').classList.remove('hidden');
}

function closeConfigModal() {
  document.getElementById('config-modal').classList.add('hidden');
}

async function submitConfig() {
  const strategy = document.getElementById('cfg-strategy').value;
  const threshold = (parseFloat(document.getElementById('cfg-threshold').value) || 5) / 100;
  const cooldown = parseInt(document.getElementById('cfg-cooldown').value) || 900;
  const autoRefreshEl = document.getElementById('cfg-auto-refresh');
  const autoRefresh = autoRefreshEl ? parseInt(autoRefreshEl.value) : 300;
  const autoRelaunchEl = document.getElementById('cfg-auto-relaunch');
  const autoRelaunch = autoRelaunchEl ? autoRelaunchEl.checked : false;
  const apikey = document.getElementById('cfg-apikey').value.trim();

  try {
    await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rotation_strategy: strategy,
        min_quota_threshold: threshold,
        cooldown_seconds_on_429: cooldown,
        auto_refresh_quota_interval: isNaN(autoRefresh) ? 300 : autoRefresh,
        auto_relaunch_antigravity: autoRelaunch,
        api_key: apikey
      })
    });
    showToast('Đã lưu cấu hình Gateway & Tự động Relaunch!');
    loadData();
  } catch (err) {
    showToast('Lỗi: ' + err, true);
  }
}

function copyToClipboard(elementId) {
  const text = document.getElementById(elementId).innerText;
  navigator.clipboard.writeText(text);
  showToast(`Đã sao chép: ${text}`);
}

async function clearRotationLogs() {
  await fetch('/api/rotations/clear', { method: 'POST' });
  showToast('Đã xóa lịch sử xoay tài khoản.');
  loadData();
}
