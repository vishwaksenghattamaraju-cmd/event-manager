/**
 * Events and Booking Engine Controller - Lu.ma Studio Edition
 * Features:
 * - Two-column Lu.ma event studio layout with live timeline & options
 * - Zero images in artwork card (clean placeholder per request)
 * - Live inventory availability checking with debouncing & shortage alerts
 * - AI auto-recommendations and seamless tab switching to scheduled bookings
 */

let allEvents = [];
let catalogItems = [];
let checkAvailabilityTimer = null;
let lastAvailabilityResult = null;
let currentUser = null;
let currentArtworkDataUrl = null;

document.addEventListener('DOMContentLoaded', async () => {
  currentUser = await API.getCurrentUser();
  await UI.initNavbar();

  setupStudioTabs();
  setupFilterHandlers();
  setupModalHandlers();
  initDateTimePickers();
  initMetaPills();
  initArtworkDropzone();

  await loadCatalogItems();
  await loadEvents();

  // Add 1 initial item picker row in the studio
  addItemPickerRow();

  // Button handlers
  document.getElementById('btn-add-item-row')?.addEventListener('click', () => addItemPickerRow());
  document.getElementById('btn-ai-recommend')?.addEventListener('click', handleAiRecommend);
  document.getElementById('btn-table-new-event')?.addEventListener('click', () => switchTab('create'));

  // Booking submissions
  document.getElementById('form-booking')?.addEventListener('submit', (e) => {
    e.preventDefault();
    submitBooking('CONFIRMED');
  });

  document.getElementById('btn-submit-draft')?.addEventListener('click', () => {
    submitBooking('DRAFT');
  });

  // Listen for role toggle
  window.addEventListener('roleChanged', (e) => {
    if (e.detail && e.detail.user) {
      currentUser = e.detail.user;
      loadEvents();
    }
  });
});

/* ==========================================================================
   Studio Tab Switching (Create Event vs. Scheduled Bookings)
   ========================================================================== */
function setupStudioTabs() {
  const tabCreate = document.getElementById('tab-btn-create');
  const tabBookings = document.getElementById('tab-btn-bookings');

  tabCreate?.addEventListener('click', () => switchTab('create'));
  tabBookings?.addEventListener('click', () => switchTab('bookings'));
}

function switchTab(target) {
  const tabCreate = document.getElementById('tab-btn-create');
  const tabBookings = document.getElementById('tab-btn-bookings');
  const panelCreate = document.getElementById('panel-create-event');
  const panelBookings = document.getElementById('panel-scheduled-bookings');

  if (target === 'create') {
    tabCreate?.classList.add('active');
    tabCreate?.setAttribute('aria-selected', 'true');
    tabBookings?.classList.remove('active');
    tabBookings?.setAttribute('aria-selected', 'false');

    if (panelCreate) panelCreate.style.display = 'grid';
    if (panelBookings) panelBookings.style.display = 'none';
  } else {
    tabBookings?.classList.add('active');
    tabBookings?.setAttribute('aria-selected', 'true');
    tabCreate?.classList.remove('active');
    tabCreate?.setAttribute('aria-selected', 'false');

    if (panelCreate) panelCreate.style.display = 'none';
    if (panelBookings) panelBookings.style.display = 'block';
    renderEventsTable();
  }
}

/* ==========================================================================
   Date & Time Pickers + Timezone Synchronization
   ========================================================================== */
function initDateTimePickers() {
  const startDateInput = document.getElementById('picker-start-date');
  const startTimeInput = document.getElementById('picker-start-time');
  const endDateInput = document.getElementById('picker-end-date');
  const endTimeInput = document.getElementById('picker-end-time');

  const hiddenStart = document.getElementById('booking-start');
  const hiddenEnd = document.getElementById('booking-end');

  // Default times: Tomorrow 10:00 to 18:00
  const now = new Date();
  const start = new Date(now);
  start.setDate(start.getDate() + 1);
  start.setHours(10, 0, 0, 0);

  const end = new Date(start);
  end.setHours(18, 0, 0, 0);

  const pad = (n) => String(n).padStart(2, '0');
  const formatDateVal = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const formatTimeVal = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;

  if (startDateInput) startDateInput.value = formatDateVal(start);
  if (startTimeInput) startTimeInput.value = formatTimeVal(start);
  if (endDateInput) endDateInput.value = formatDateVal(end);
  if (endTimeInput) endTimeInput.value = formatTimeVal(end);

  function syncToHidden() {
    if (startDateInput && startTimeInput && hiddenStart) {
      hiddenStart.value = `${startDateInput.value}T${startTimeInput.value}`;
    }
    if (endDateInput && endTimeInput && hiddenEnd) {
      hiddenEnd.value = `${endDateInput.value}T${endTimeInput.value}`;
    }
    triggerLiveAvailabilityCheck();
  }

  startDateInput?.addEventListener('change', syncToHidden);
  startTimeInput?.addEventListener('change', syncToHidden);
  endDateInput?.addEventListener('change', syncToHidden);
  endTimeInput?.addEventListener('change', syncToHidden);

  // Initial sync
  syncToHidden();

  // Detect and set local timezone labels
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata';
    const city = tz.split('/').pop().replace(/_/g, ' ') || 'Kolkata';
    const offsetMin = -new Date().getTimezoneOffset();
    const sign = offsetMin >= 0 ? '+' : '-';
    const absMin = Math.abs(offsetMin);
    const hrs = pad(Math.floor(absMin / 60));
    const mins = pad(absMin % 60);
    const gmtStr = `GMT${sign}${hrs}:${mins}`;

    const tzGmtEl = document.getElementById('tz-gmt-label');
    const tzCityEl = document.getElementById('tz-city-label');
    if (tzGmtEl) tzGmtEl.textContent = gmtStr;
    if (tzCityEl) tzCityEl.textContent = city;
  } catch (e) {
    console.warn('Timezone detection fallback', e);
  }
}

/* ==========================================================================
   Metadata Pill Synchronisation & Quick Toggles
   ========================================================================== */
function initMetaPills() {
  const pillCalendar = document.getElementById('pill-calendar-select');
  const labelCalendar = document.getElementById('calendar-name-label');
  const pillVisibility = document.getElementById('pill-visibility-select');
  const labelVisibility = document.getElementById('visibility-label');

  const calendars = ['Personal Calendar', 'Company Events', 'Community Hub', 'Private Workspace'];
  let calIdx = 0;

  pillCalendar?.addEventListener('click', () => {
    calIdx = (calIdx + 1) % calendars.length;
    if (labelCalendar) labelCalendar.textContent = calendars[calIdx];
    if (window.UI?.toast) UI.toast(`Switched calendar to ${calendars[calIdx]}`, 'info');
  });

  const visibilities = [
    { label: 'Public', icon: '🌐' },
    { label: 'Private', icon: '🔒' },
    { label: 'Unlisted', icon: '🔗' }
  ];
  let visIdx = 0;

  pillVisibility?.addEventListener('click', () => {
    visIdx = (visIdx + 1) % visibilities.length;
    const v = visibilities[visIdx];
    if (labelVisibility) labelVisibility.textContent = v.label;
    const iconSpan = pillVisibility.querySelector('span:first-child');
    if (iconSpan) iconSpan.textContent = v.icon;
    if (window.UI?.toast) UI.toast(`Event visibility set to ${v.label}`, 'info');
  });
}

/* ==========================================================================
   AI-Generated Artwork Preset Engine & Semantic Matcher
   ========================================================================== */
const AI_ARTWORK_PRESETS = [
  // Primary category presets matching select options
  {
    key: 'conference',
    category: 'conference',
    label: 'Keynote Tech Conference',
    src: '/images/events/conference.jpg',
    keywords: ['conference', 'keynote', 'summit', 'convention', 'expo', 'forum', 'symposium', 'speaker']
  },
  {
    key: 'workshop',
    category: 'workshop',
    label: 'Creative Collaborative Workshop',
    src: '/images/events/workshop.jpg',
    keywords: ['workshop', 'training', 'masterclass', 'bootcamp', 'hands-on', 'lab', 'class', 'learn', 'hackathon']
  },
  {
    key: 'wedding',
    category: 'wedding',
    label: 'Luxury Wedding Reception',
    src: '/images/events/wedding.jpg',
    keywords: ['wedding', 'reception', 'marriage', 'bridal', 'ceremony', 'bride', 'groom', 'anniversary']
  },
  {
    key: 'concert',
    category: 'concert',
    label: 'Live Music & Laser Stage Concert',
    src: '/images/events/concert.jpg',
    keywords: ['concert', 'live music', 'festival', 'band', 'dj', 'rave', 'stage', 'rock', 'synth', 'show', 'edm']
  },
  {
    key: 'corporate',
    category: 'corporate',
    label: 'Executive Skyline Gala',
    src: '/images/events/corporate.jpg',
    keywords: ['corporate', 'business', 'executive', 'gala', 'board', 'annual meeting', 'leadership', 'client', 'dinner']
  },
  {
    key: 'meetup',
    category: 'meetup',
    label: 'Cocktail Networking Lounge',
    src: '/images/events/cocktail-hour.jpg',
    keywords: ['meetup', 'networking', 'social', 'mixer', 'drinks', 'cocktail', 'gathering', 'community']
  },

  // Description / Title semantic matches:
  {
    key: 'yoga',
    category: null,
    label: 'Sunset Yoga & Wellness',
    src: '/images/events/sunset-yoga.jpg',
    keywords: ['yoga', 'wellness', 'fitness', 'meditation', 'pilates', 'mindfulness', 'retreat', 'health', 'zen']
  },
  {
    key: 'dinner',
    category: null,
    label: 'Celebration Feast & Dinner Party',
    src: '/images/events/dinner-party.jpg',
    keywords: ['dinner', 'party', 'birthday', 'celebration', 'feast', 'banquet', 'culinary', 'tasting menu', 'food', 'supper', 'bday']
  },
  {
    key: 'acoustic',
    category: null,
    label: 'Acoustic & Unplugged Session',
    src: '/images/events/acoustic-session.jpg',
    keywords: ['acoustic', 'unplugged', 'guitar', 'indie', 'intimate', 'singer', 'songwriter', 'folk', 'jazz']
  },
  {
    key: 'tech_salon',
    category: null,
    label: 'AI & Future Tech Salon',
    src: '/images/events/ai-salon.jpg',
    keywords: ['ai', 'artificial intelligence', 'machine learning', 'deep learning', 'algorithm', 'neural', 'robotics', 'software', 'cloud', 'cyber']
  },
  {
    key: 'clay_craft',
    category: null,
    label: 'Pottery & Craft Workshop',
    src: '/images/events/clay-craft.jpg',
    keywords: ['pottery', 'clay', 'ceramic', 'craft', 'sculpture', 'painting', 'diy', 'art class', 'art studio', 'handicraft']
  },
  {
    key: 'brew_lab',
    category: null,
    label: 'Craft Brewery & Hops Lab',
    src: '/images/events/brew-lab.jpg',
    keywords: ['beer', 'brew', 'brewery', 'cider', 'wine', 'ale', 'hops', 'pub', 'tasting']
  },
  {
    key: 'gaming',
    category: null,
    label: 'Game Night & Poker Lounge',
    src: '/images/events/poker-night.jpg',
    keywords: ['poker', 'game night', 'casino', 'board games', 'cards', 'trivia', 'esports', 'tournament']
  }
];

let isUserCustomUpload = false;
let currentAiCycleIndex = 0;

function initArtworkDropzone() {
  const uploadBtn = document.getElementById('btn-artwork-upload');
  const magicBtn = document.getElementById('btn-artwork-magic');
  const dropzone = document.getElementById('artwork-dropzone');
  const fileInput = document.getElementById('artwork-file-input');
  const previewImg = document.getElementById('artwork-preview-img');
  const placeholder = document.getElementById('artwork-placeholder');
  const removeBtn = document.getElementById('btn-artwork-remove');
  const aiBadge = document.getElementById('artwork-ai-badge');
  const aiLabel = document.getElementById('artwork-ai-label');

  const typeSelect = document.getElementById('booking-type');
  const titleInput = document.getElementById('booking-title');
  const descInput = document.getElementById('booking-description');

  if (!dropzone || !fileInput) return;

  function findMatchingPresets(categoryVal, titleVal, descVal) {
    const text = `${titleVal || ''} ${descVal || ''}`.toLowerCase();
    const cat = (categoryVal || '').toLowerCase();

    // 1. Check for specific semantic theme matches in title & description
    const specificMatches = AI_ARTWORK_PRESETS.filter(p => 
      p.keywords.some(kw => text.includes(kw))
    );
    if (specificMatches.length > 0) {
      return specificMatches;
    }

    // 2. Filter by category
    const categoryMatches = AI_ARTWORK_PRESETS.filter(p => p.category === cat);
    if (categoryMatches.length > 0) {
      return categoryMatches;
    }

    // 3. Fallback
    return [AI_ARTWORK_PRESETS[0]];
  }

  function autoMatchArtwork(forceCycle = false) {
    if (isUserCustomUpload) return;

    const cat = typeSelect ? typeSelect.value : 'Conference';
    const title = titleInput ? titleInput.value : '';
    const desc = descInput ? descInput.value : '';

    const matches = findMatchingPresets(cat, title, desc);

    if (forceCycle) {
      currentAiCycleIndex = (currentAiCycleIndex + 1) % AI_ARTWORK_PRESETS.length;
      const cycledPreset = AI_ARTWORK_PRESETS[currentAiCycleIndex];
      applyPreset(cycledPreset);
      UI.toast(`✨ Cycled artwork to ${cycledPreset.label}`, 'info');
      return;
    }

    const selectedPreset = matches[0] || AI_ARTWORK_PRESETS[0];
    applyPreset(selectedPreset);
  }

  function applyPreset(preset) {
    currentArtworkDataUrl = preset.src;

    if (previewImg) {
      previewImg.src = preset.src;
      previewImg.style.display = 'block';
    }
    if (placeholder) {
      placeholder.style.display = 'none';
    }
    if (aiBadge) {
      aiBadge.style.display = 'flex';
      if (aiLabel) aiLabel.textContent = `AI Matched: ${preset.label}`;
    }
    if (removeBtn) {
      removeBtn.style.display = 'flex';
      removeBtn.title = 'Reset to AI Default';
    }
    dropzone.classList.add('has-image');
  }

  function setCustomArtwork(dataUrl) {
    isUserCustomUpload = true;
    currentArtworkDataUrl = dataUrl;
    if (previewImg) {
      previewImg.src = dataUrl;
      previewImg.style.display = 'block';
    }
    if (placeholder) {
      placeholder.style.display = 'none';
    }
    if (aiBadge) {
      aiBadge.style.display = 'flex';
      if (aiLabel) aiLabel.textContent = '📷 Custom Photo Uploaded';
    }
    if (removeBtn) {
      removeBtn.style.display = 'flex';
      removeBtn.title = 'Remove custom photo';
    }
    dropzone.classList.add('has-image');
  }

  function resetArtwork() {
    isUserCustomUpload = false;
    fileInput.value = '';
    autoMatchArtwork();
    UI.toast('Reset to AI category artwork', 'info');
  }

  function handleFile(file) {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      UI.toast('Please select a valid image file (PNG, JPG, WebP, GIF)', 'warning');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      UI.toast('Image size is too large (max 10MB)', 'warning');
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      setCustomArtwork(e.target.result);
      UI.toast('Custom artwork added!', 'success');
    };
    reader.onerror = () => {
      UI.toast('Failed to load image file', 'error');
    };
    reader.readAsDataURL(file);
  }

  // Upload button
  uploadBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput.click();
  });

  // Magic AI Cycle button
  magicBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    isUserCustomUpload = false;
    autoMatchArtwork(true);
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0]);
    }
  });

  removeBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    resetArtwork();
  });

  // Drag and drop events
  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('drag-over');
    });
  });

  ['dragleave', 'dragend', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('drag-over');
    });
  });

  dropzone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    if (dt && dt.files && dt.files.length > 0) {
      handleFile(dt.files[0]);
    }
  });

  // Clipboard paste
  window.addEventListener('paste', (e) => {
    const items = (e.clipboardData || e.originalEvent?.clipboardData)?.items;
    if (!items) return;
    for (const item of items) {
      if (item.type.indexOf('image') !== -1) {
        const file = item.getAsFile();
        if (file) {
          handleFile(file);
          break;
        }
      }
    }
  });

  // Real-time automatic AI artwork updates based on category & description
  typeSelect?.addEventListener('change', () => {
    isUserCustomUpload = false;
    autoMatchArtwork();
  });

  let debounceTimer = null;
  function debouncedAutoMatch() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      autoMatchArtwork();
    }, 300);
  }

  titleInput?.addEventListener('input', debouncedAutoMatch);
  descInput?.addEventListener('input', debouncedAutoMatch);

  // Initialize immediately on page load
  autoMatchArtwork();

  window.clearArtwork = resetArtwork;
  window.setArtwork = setCustomArtwork;
}

/* ==========================================================================
   AI Item Recommendations
   ========================================================================== */
async function handleAiRecommend() {
  const btn = document.getElementById('btn-ai-recommend');
  const eventType = document.getElementById('booking-type').value;
  const attendees = parseInt(document.getElementById('booking-attendees').value, 10) || 50;
  const startTime = document.getElementById('booking-start').value;
  const endTime = document.getElementById('booking-end').value;

  let duration = 4.0;
  if (startTime && endTime) {
    const diffMs = new Date(endTime) - new Date(startTime);
    if (diffMs > 0) {
      duration = Math.max(1.0, Math.round((diffMs / (1000 * 60 * 60)) * 10) / 10);
    }
  }

  btn.disabled = true;
  btn.textContent = '⚡ Analyzing...';

  const res = await API.fetch('/api/ml/predict-items', {
    method: 'POST',
    body: JSON.stringify({
      event_type: eventType,
      expected_guests: attendees,
      duration_hours: duration,
      start_time: startTime,
      respect_stock: false
    })
  });

  btn.disabled = false;
  btn.textContent = '⚡ AI Auto-Recommend';

  if (!res.ok) {
    UI.toast('AI prediction failed: ' + res.error, 'error');
    return;
  }

  const items = res.data.items || [];
  if (items.length === 0) {
    UI.toast('No item recommendations generated.', 'warning');
    return;
  }

  const list = document.getElementById('booking-items-list');
  list.innerHTML = '';

  items.forEach(rec => {
    if (rec.suggested_quantity > 0) {
      let matchedCatalogId = rec.item_id;
      if (!matchedCatalogId) {
        const found = catalogItems.find(c => 
          c.category.toLowerCase() === rec.category.toLowerCase() ||
          c.name.toLowerCase().includes(rec.item_key.toLowerCase())
        );
        if (found) matchedCatalogId = found.id;
      }
      addItemPickerRow(matchedCatalogId || '', rec.suggested_quantity);
    }
  });

  UI.toast(`⚡ Loaded AI equipment recommendations for ${attendees} guests!`, 'success');
  triggerLiveAvailabilityCheck();
}

/* ==========================================================================
   Catalog & Events Data Loading
   ========================================================================== */
async function loadCatalogItems() {
  const res = await API.fetch('/api/inventory/items');
  if (res.ok) {
    catalogItems = (res.data.items || []).filter(i => i.is_active);
  }
}

const LOCAL_STORAGE_EVENTS_KEY = 'event_inventory_user_events';

function getLocalEvents() {
  try {
    return JSON.parse(localStorage.getItem(LOCAL_STORAGE_EVENTS_KEY) || '[]');
  } catch (e) {
    return [];
  }
}

function saveLocalEvents(events) {
  try {
    localStorage.setItem(LOCAL_STORAGE_EVENTS_KEY, JSON.stringify(events));
  } catch (e) {
    console.warn('Could not cache events in localStorage', e);
  }
}

async function loadEvents() {
  const tbody = document.getElementById('events-tbody');
  const res = await API.fetch('/api/events');
  const localList = getLocalEvents();

  let fetchedEvents = [];
  if (res.ok && res.data && Array.isArray(res.data.events)) {
    fetchedEvents = res.data.events;
  }

  // Resilient Merge: Keep any locally created events so that events NEVER disappear
  // across ephemeral serverless container cold-starts.
  const mergedMap = new Map();

  // Add backend events first
  fetchedEvents.forEach(evt => {
    mergedMap.set(String(evt.id), evt);
  });

  // Merge any locally stored events missing from backend response
  const missingFromBackend = [];
  localList.forEach(localEvt => {
    const key = String(localEvt.id);
    if (!mergedMap.has(key)) {
      mergedMap.set(key, localEvt);
      missingFromBackend.push(localEvt);
    } else {
      // Keep enriched fields if available
      mergedMap.set(key, { ...localEvt, ...mergedMap.get(key) });
    }
  });

  allEvents = Array.from(mergedMap.values());
  saveLocalEvents(allEvents);

  const badge = document.getElementById('bookings-count-badge');
  if (badge) badge.textContent = allEvents.length;

  renderEventsTable();

  // Self-heal: If an event existed in local cache but is missing from this backend container,
  // sync it in background so the container DB also gets it.
  if (missingFromBackend.length > 0) {
    syncMissingEventsToBackend(missingFromBackend);
  }
}

async function syncMissingEventsToBackend(events) {
  for (const evt of events) {
    if (String(evt.id).startsWith('local-')) {
      try {
        const payload = {
          title: evt.name || evt.title,
          location: evt.location || '',
          event_type: evt.event_type || 'other',
          expected_attendees: evt.expected_attendees || evt.expected_guest_count || 50,
          start_time: evt.start_time,
          end_time: evt.end_time,
          description: evt.description || '',
          status: evt.status || 'DRAFT',
          image_url: evt.image_url || '',
          items: (evt.items || []).map(i => ({
            inventory_item_id: i.item_id || i.inventory_item_id,
            quantity_requested: i.quantity || i.quantity_requested || 1
          }))
        };
        const res = await API.fetch('/api/events', {
          method: 'POST',
          body: JSON.stringify(payload)
        });
        if (res.ok && res.data?.event) {
          const srvEvt = res.data.event;
          allEvents = allEvents.map(e => String(e.id) === String(evt.id) ? srvEvt : e);
          saveLocalEvents(allEvents);
        }
      } catch (e) {
        console.warn('Sync fallback error:', e);
      }
    }
  }
}

function renderEventsTable() {
  const tbody = document.getElementById('events-tbody');
  const query = (document.getElementById('event-search')?.value || '').toLowerCase().trim();
  const statusFilter = (document.getElementById('filter-event-status')?.value || '').toLowerCase();

  const filtered = allEvents.filter(evt => {
    const title = evt.name || evt.title || '';
    if (query && !title.toLowerCase().includes(query) && !(evt.description || '').toLowerCase().includes(query)) {
      return false;
    }
    if (statusFilter && (evt.status || '').toLowerCase() !== statusFilter) {
      return false;
    }
    return true;
  });

  // Sort newest created and upcoming first so new events are immediately visible at the top!
  filtered.sort((a, b) => {
    const aTime = new Date(a.created_at || a.start_time).getTime();
    const bTime = new Date(b.created_at || b.start_time).getTime();
    return bTime - aTime;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; color: var(--luma-text-muted); padding: 2.5rem;">
          No events found matching your search.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered.map(evt => {
    const windowText = `${UI.formatDate(evt.start_time)}<br><span style="color: var(--luma-text-dim);">&darr; ${UI.formatDate(evt.end_time)}</span>`;
    const itemCount = (evt.items || []).reduce((sum, i) => sum + (i.quantity || i.quantity_requested || 0), 0);
    const itemLabel = `${(evt.items || []).length} items (${itemCount} units)`;
    const title = evt.name || evt.title || 'Untitled Event';

    const status = (evt.status || '').toUpperCase();
    let actionsHtml = `<button class="btn btn-secondary btn-sm" onclick="viewEventDetails(${evt.id})">Details</button>`;

    if (status === 'DRAFT') {
      actionsHtml += `
        <button class="btn btn-primary btn-sm" style="margin-left: 0.35rem;" onclick="confirmBooking(${evt.id})">Confirm</button>
        <button class="btn btn-danger btn-sm" style="margin-left: 0.35rem;" onclick="cancelBooking(${evt.id})">Cancel</button>
      `;
    } else if (status === 'CONFIRMED') {
      actionsHtml += `
        <button class="btn btn-secondary btn-sm" style="margin-left: 0.35rem; color: var(--success);" onclick="completeBooking(${evt.id})">Complete</button>
        <button class="btn btn-danger btn-sm" style="margin-left: 0.35rem;" onclick="cancelBooking(${evt.id})">Cancel</button>
      `;
    }

    return `
      <tr>
        <td>
          <div style="display: flex; align-items: center; gap: 0.75rem;">
            ${evt.image_url ? `<img src="${escapeHtml(evt.image_url)}" alt="Artwork" style="width: 44px; height: 44px; border-radius: 10px; object-fit: cover; flex-shrink: 0; border: 1px solid rgba(255,255,255,0.12);">` : ''}
            <div>
              <strong style="color: var(--luma-text-main, #ffffff);">${escapeHtml(title)}</strong>
              ${evt.location ? `<div style="font-size: 0.8rem; color: var(--luma-text-muted);">📍 ${escapeHtml(evt.location)}</div>` : ''}
              ${evt.description ? `<div style="font-size: 0.8rem; color: var(--luma-text-dim);">${escapeHtml(evt.description)}</div>` : ''}
            </div>
          </div>
        </td>
        <td style="text-transform: capitalize;">${escapeHtml(evt.event_type)}</td>
        <td style="font-size: 0.85rem;">${windowText}</td>
        <td>${evt.expected_attendees || '—'}</td>
        <td>${itemLabel}</td>
        <td>${UI.statusBadge(evt.status)}</td>
        <td><div style="display: flex; align-items: center;">${actionsHtml}</div></td>
      </tr>
    `;
  }).join('');
}

function setupFilterHandlers() {
  document.getElementById('event-search')?.addEventListener('input', renderEventsTable);
  document.getElementById('filter-event-status')?.addEventListener('change', renderEventsTable);
}

function setupModalHandlers() {
  document.querySelectorAll('[data-close]').forEach(btn => {
    btn.addEventListener('click', () => {
      const modalId = btn.getAttribute('data-close');
      document.getElementById(modalId)?.classList.remove('open');
    });
  });

  document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) backdrop.classList.remove('open');
    });
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-backdrop.open').forEach(m => m.classList.remove('open'));
    }
  });
}

/* ==========================================================================
   Item Picker Rows & Dynamic Catalog
   ========================================================================== */
function addItemPickerRow(selectedItemId = '', quantity = 1) {
  const list = document.getElementById('booking-items-list');
  if (!list) return;

  const rowId = 'picker-row-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
  const row = document.createElement('div');
  row.className = 'item-picker-row';
  row.id = rowId;

  const optionsHtml = catalogItems.map(item => {
    const selected = item.id == selectedItemId ? 'selected' : '';
    return `<option value="${item.id}" ${selected}>${escapeHtml(item.name)} (${item.category} &bull; ${item.sku})</option>`;
  }).join('');

  row.innerHTML = `
    <select class="form-select item-picker-select" onchange="triggerLiveAvailabilityCheck()">
      <option value="">-- Choose item from catalog --</option>
      ${optionsHtml}
    </select>
    <input type="number" class="form-input item-picker-qty" min="1" value="${quantity}" placeholder="Qty" oninput="triggerLiveAvailabilityCheck()" style="width: 85px;">
    <button type="button" class="btn btn-secondary btn-sm item-picker-remove-btn" style="color: var(--danger); border-radius: 8px;" onclick="removeItemPickerRow('${rowId}')">&times;</button>
  `;

  list.appendChild(row);
  triggerLiveAvailabilityCheck();
}

window.removeItemPickerRow = function(rowId) {
  document.getElementById(rowId)?.remove();
  triggerLiveAvailabilityCheck();
};

function getSelectedBookingItems() {
  const items = [];
  const rows = document.querySelectorAll('.item-picker-row');

  rows.forEach(row => {
    const select = row.querySelector('.item-picker-select');
    const qtyInput = row.querySelector('.item-picker-qty');
    const itemId = parseInt(select?.value, 10);
    const qty = parseInt(qtyInput?.value, 10);

    if (itemId && qty > 0) {
      items.push({ inventory_item_id: itemId, quantity_requested: qty });
    }
  });

  return items;
}

/* ==========================================================================
   Live Availability Checking
   ========================================================================== */
window.triggerLiveAvailabilityCheck = function() {
  clearTimeout(checkAvailabilityTimer);
  checkAvailabilityTimer = setTimeout(checkLiveAvailability, 300);
};

async function checkLiveAvailability() {
  const previewBox = document.getElementById('availability-preview');
  const msgEl = document.getElementById('availability-message');
  const shortagesList = document.getElementById('availability-shortages');
  const submitConfirmBtn = document.getElementById('btn-submit-confirm');

  if (!previewBox || !msgEl || !shortagesList) return;

  const startTime = document.getElementById('booking-start')?.value;
  const endTime = document.getElementById('booking-end')?.value;
  const items = getSelectedBookingItems();

  if (!startTime || !endTime || items.length === 0) {
    previewBox.style.display = 'none';
    return;
  }

  previewBox.style.display = 'block';
  previewBox.className = 'availability-box checking';
  msgEl.innerHTML = '⚡ Checking warehouse &amp; reservation calendar...';
  shortagesList.style.display = 'none';

  const payload = {
    start_time: startTime,
    end_time: endTime,
    items: items
  };

  const res = await API.fetch('/api/events/check-availability', {
    method: 'POST',
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    previewBox.className = 'availability-box shortage';
    msgEl.innerHTML = `⚠️ Availability check error: ${escapeHtml(res.error)}`;
    return;
  }

  lastAvailabilityResult = res.data;
  const isAvailable = res.data.is_sufficient !== undefined ? res.data.is_sufficient : Boolean(res.data.available);

  if (isAvailable) {
    previewBox.className = 'availability-box available';
    msgEl.innerHTML = '✓ All requested items are fully available for this time window!';
    shortagesList.style.display = 'none';
    if (submitConfirmBtn) submitConfirmBtn.disabled = false;
  } else {
    previewBox.className = 'availability-box shortage';
    msgEl.innerHTML = `<strong>⚠️ Shortage Detected!</strong> Cannot confirm booking due to conflicting reservations or warehouse limits:`;

    shortagesList.innerHTML = (res.data.shortages || []).map(s => {
      const shortageAmount = s.short_by || s.shortage || 0;
      const itemId = s.item_id || s.inventory_item_id;
      const itemName = s.item_name || `Item #${itemId}`;
      return `
        <li class="shortage-item">
          <span><strong>${escapeHtml(itemName)}</strong></span>
          <span>Requested: <strong>${s.requested}</strong> | Available: <strong>${s.available}</strong> (Deficit: -${shortageAmount})</span>
        </li>
      `;
    }).join('');
    shortagesList.style.display = 'block';
  }
}

/* ==========================================================================
   Submit Booking (Create Event / Save as Draft)
   ========================================================================== */
async function submitBooking(status) {
  const title = document.getElementById('booking-title')?.value.trim();
  const location = document.getElementById('booking-location')?.value.trim();
  const eventType = document.getElementById('booking-type')?.value;
  const attendees = parseInt(document.getElementById('booking-attendees')?.value, 10);
  const startTime = document.getElementById('booking-start')?.value;
  const endTime = document.getElementById('booking-end')?.value;
  const description = document.getElementById('booking-description')?.value.trim();
  const items = getSelectedBookingItems();

  if (!title) {
    UI.toast('Please enter an event name.', 'error');
    document.getElementById('booking-title')?.focus();
    return;
  }

  if (!startTime || !endTime) {
    UI.toast('Please select event start and end times.', 'error');
    return;
  }

  if (new Date(startTime) >= new Date(endTime)) {
    UI.toast('Event start time must precede end time.', 'error');
    return;
  }

  if (items.length === 0) {
    UI.toast('Please select at least one item from the warehouse catalog.', 'error');
    return;
  }

  // If user requested CONFIRMED but availability check detected shortage,
  // save as DRAFT gracefully instead of dropping/aborting the booking!
  let requestedStatus = status;
  let hasShortage = false;
  if (status === 'CONFIRMED' && lastAvailabilityResult && !lastAvailabilityResult.available) {
    hasShortage = true;
    requestedStatus = 'DRAFT';
  }

  const payload = {
    title,
    location,
    event_type: eventType,
    expected_attendees: attendees,
    start_time: startTime,
    end_time: endTime,
    description,
    status: requestedStatus,
    image_url: currentArtworkDataUrl || '',
    items
  };

  const submitBtn = status === 'CONFIRMED' ? document.getElementById('btn-submit-confirm') : document.getElementById('btn-submit-draft');
  if (submitBtn) submitBtn.disabled = true;

  const res = await API.fetch('/api/events', {
    method: 'POST',
    body: JSON.stringify(payload)
  });

  if (submitBtn) submitBtn.disabled = false;

  // Resilient handling: accept 200/201 (success) AND 409 (created as draft with conflict)
  if (res.ok || (res.status === 409 && (res.data?.event || res.details?.event))) {
    const createdEvent = res.data?.event || res.details?.event || {
      id: 'local-' + Date.now(),
      name: title,
      title: title,
      location,
      event_type: eventType,
      expected_attendees: attendees,
      start_time: startTime,
      end_time: endTime,
      description,
      status: requestedStatus.toLowerCase(),
      image_url: currentArtworkDataUrl || '',
      items: items.map(it => ({
        inventory_item_id: it.inventory_item_id,
        quantity: it.quantity_requested
      }))
    };

    // Immediately cache to localStorage so it can NEVER disappear
    const currentLocal = getLocalEvents();
    const updated = [createdEvent, ...currentLocal.filter(e => String(e.id) !== String(createdEvent.id))];
    saveLocalEvents(updated);

    if (hasShortage || res.status === 409) {
      UI.toast(`Event "${title}" saved to Scheduled Bookings as Draft (inventory shortage). Review and confirm when stock is available.`, 'warning');
    } else {
      UI.toast(`Event "${title}" ${requestedStatus.toLowerCase()} successfully!`, 'success');
    }

    // Reset filters so the new event is 100% visible immediately in table
    const searchInput = document.getElementById('event-search');
    const filterSelect = document.getElementById('filter-event-status');
    if (searchInput) searchInput.value = '';
    if (filterSelect) filterSelect.value = '';

    // Reset form and add 1 default item row
    document.getElementById('form-booking').reset();
    document.getElementById('booking-items-list').innerHTML = '';
    window.clearArtwork?.();
    addItemPickerRow();
    initDateTimePickers();

    await loadEvents();

    // Smoothly show the Scheduled Bookings panel to view the created event
    switchTab('bookings');
  } else {
    UI.toast(`Booking error: ${res.error || 'Server error'}`, 'error');
  }
}

/* ==========================================================================
   Booking Actions (Confirm, Complete, Cancel, View Details)
   ========================================================================== */
window.confirmBooking = async function(eventId) {
  if (!confirm('Are you sure you want to confirm this booking and reserve inventory?')) return;
  const res = await API.fetch(`/api/events/${eventId}/confirm`, { method: 'POST' });
  if (res.ok) {
    UI.toast('Booking confirmed and inventory reserved!', 'success');
    allEvents = allEvents.map(e => e.id === eventId ? { ...e, status: 'confirmed' } : e);
    saveLocalEvents(allEvents);
    renderEventsTable();
    await loadEvents();
  } else {
    UI.toast(`Cannot confirm booking: ${res.error}`, 'error');
  }
};

window.cancelBooking = async function(eventId) {
  if (!confirm('Cancel this event booking and release reserved items?')) return;
  const res = await API.fetch(`/api/events/${eventId}/cancel`, { method: 'POST' });
  if (res.ok) {
    UI.toast('Booking cancelled. Reserved stock released back to catalog.', 'info');
    allEvents = allEvents.map(e => e.id === eventId ? { ...e, status: 'cancelled' } : e);
    saveLocalEvents(allEvents);
    renderEventsTable();
    await loadEvents();
  } else {
    UI.toast(`Cancellation failed: ${res.error}`, 'error');
  }
};

window.completeBooking = async function(eventId) {
  if (!confirm('Mark event completed? Any consumable items will be permanently deducted from inventory.')) return;
  const res = await API.fetch(`/api/events/${eventId}/complete`, { method: 'POST' });
  if (res.ok) {
    UI.toast('Event completed successfully!', 'success');
    allEvents = allEvents.map(e => e.id === eventId ? { ...e, status: 'completed' } : e);
    saveLocalEvents(allEvents);
    renderEventsTable();
    await loadEvents();
  } else {
    UI.toast(`Completion failed: ${res.error}`, 'error');
  }
};

window.viewEventDetails = function(eventId) {
  const evt = allEvents.find(e => e.id === eventId);
  if (!evt) return;

  document.getElementById('details-title').textContent = evt.name || evt.title || 'Event Details';
  const content = document.getElementById('details-content');

  const itemsList = (evt.items || []).map(i => `
    <li style="display: flex; justify-content: space-between; padding: 0.4rem 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
      <span>${escapeHtml(i.item ? i.item.name : 'Item #' + i.inventory_item_id)}</span>
      <strong>${i.quantity_requested || i.quantity || 0} units</strong>
    </li>
  `).join('') || '<p style="color: var(--luma-text-muted);">No items reserved.</p>';

  content.innerHTML = `
    ${evt.image_url ? `
      <div style="margin-bottom: 1.25rem; border-radius: 16px; overflow: hidden; border: 1px solid rgba(255,255,255,0.12); aspect-ratio: 16/9; max-height: 220px; background: #000;">
        <img src="${escapeHtml(evt.image_url)}" alt="${escapeHtml(evt.name || 'Event Artwork')}" style="width: 100%; height: 100%; object-fit: cover; display: block;">
      </div>
    ` : ''}
    <div style="margin-bottom: 1rem;">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <span style="color: var(--luma-text-muted); font-size: 0.9rem;">Status:</span>
        <span>${UI.statusBadge(evt.status)}</span>
      </div>
      <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.5rem;">
        <span style="color: var(--luma-text-muted); font-size: 0.9rem;">Event Type:</span>
        <strong style="text-transform: capitalize;">${escapeHtml(evt.event_type)}</strong>
      </div>
      ${evt.location ? `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.5rem;">
          <span style="color: var(--luma-text-muted); font-size: 0.9rem;">Location:</span>
          <strong>${escapeHtml(evt.location)}</strong>
        </div>
      ` : ''}
      <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.5rem;">
        <span style="color: var(--luma-text-muted); font-size: 0.9rem;">Attendees:</span>
        <strong>${evt.expected_attendees || evt.expected_guest_count || '—'}</strong>
      </div>
    </div>

    <div style="background: rgba(255,255,255,0.03); padding: 0.85rem; border-radius: var(--radius-md); margin-bottom: 1rem;">
      <div style="font-size: 0.8rem; color: var(--luma-text-muted); margin-bottom: 0.25rem;">SCHEDULE WINDOW</div>
      <div style="font-size: 0.9rem;"><strong>From:</strong> ${UI.formatDate(evt.start_time)}</div>
      <div style="font-size: 0.9rem; margin-top: 0.25rem;"><strong>To:</strong> ${UI.formatDate(evt.end_time)}</div>
    </div>

    ${evt.description ? `
      <div style="margin-bottom: 1rem;">
        <div style="font-size: 0.8rem; color: var(--luma-text-muted);">NOTES</div>
        <p style="font-size: 0.9rem;">${escapeHtml(evt.description)}</p>
      </div>
    ` : ''}

    <div>
      <div style="font-size: 0.85rem; color: var(--luma-text-muted); margin-bottom: 0.5rem; text-transform: uppercase;">Reserved Inventory Items</div>
      <ul style="list-style: none;">
        ${itemsList}
      </ul>
    </div>
  `;

  document.getElementById('modal-event-details').classList.add('open');
};

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
