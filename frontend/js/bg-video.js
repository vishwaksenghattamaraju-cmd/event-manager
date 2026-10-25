/*
 * Background Video component (reusable, dependency-free).
 *
 * Usage: add  data-bg-video="login|dashboard|inventory|events"  to <body>
 * and include this script. Exactly one <video> is created per page, only for
 * that page's assigned clip.
 */
(function () {
  'use strict';

  var BASE = '/videos/';
  var CLIPS = {
    login:     { video: 'login-bg.mp4',     poster: 'login-bg.jpg' },
    dashboard: { video: 'dashboard-bg.mp4', poster: 'dashboard-bg.jpg' },
    inventory: { video: 'inventory-bg.mp4', poster: 'inventory-bg.jpg' },
    events:    { video: 'events-bg.mp4',    poster: 'events-bg.jpg' }
  };

  function init() {
    var key = document.body && document.body.getAttribute('data-bg-video');
    var clip = key && CLIPS[key];
    if (!clip || document.querySelector('.bg-video')) return; // unknown page or already mounted

    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var conn = navigator.connection || {};
    var saveData = conn.saveData === true;

    var layer = document.createElement('div');
    layer.className = 'bg-video has-poster';
    layer.setAttribute('aria-hidden', 'true');
    layer.style.setProperty('--bg-video-poster', 'url("' + BASE + clip.poster + '")');

    var overlay = document.createElement('div');
    overlay.className = 'bg-video__overlay';

    // Reduced motion / data saver: poster + gradient only, no video download at all.
    if (reduceMotion || saveData) {
      layer.appendChild(overlay);
      document.body.insertBefore(layer, document.body.firstChild);
      return;
    }

    var video = document.createElement('video');
    video.className = 'bg-video__media';
    video.muted = true;                       // required for autoplay
    video.defaultMuted = true;
    video.loop = true;
    video.autoplay = true;
    video.playsInline = true;
    video.setAttribute('muted', '');
    video.setAttribute('playsinline', '');
    video.setAttribute('webkit-playsinline', '');
    video.setAttribute('disablepictureinpicture', '');
    video.setAttribute('tabindex', '-1');
    video.preload = 'auto';
    video.poster = BASE + clip.poster;
    video.src = BASE + clip.video;

    var userPaused = false;

    function markPlaying() { layer.classList.add('is-playing'); }
    video.addEventListener('playing', markPlaying);
    // If the file is missing/corrupt, keep the poster/gradient fallback visible.
    video.addEventListener('error', function () { layer.classList.remove('is-playing'); video.style.display = 'none'; toggle.hidden = true; });

    layer.appendChild(video);
    layer.appendChild(overlay);
    document.body.insertBefore(layer, document.body.firstChild);

    // Pause/play control (WCAG 2.2.2)
    var toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'bg-video-toggle';
    toggle.setAttribute('aria-label', 'Pause background video');
    toggle.title = 'Pause background video';
    toggle.textContent = '\u23F8';
    toggle.addEventListener('click', function () {
      if (video.paused) {
        userPaused = false;
        video.play().catch(function () {});
      } else {
        userPaused = true;
        video.pause();
      }
    });
    function syncToggle() {
      var paused = video.paused;
      toggle.textContent = paused ? '\u25B6' : '\u23F8';
      var label = paused ? 'Play background video' : 'Pause background video';
      toggle.setAttribute('aria-label', label);
      toggle.title = label;
    }
    video.addEventListener('play', syncToggle);
    video.addEventListener('pause', syncToggle);
    document.body.appendChild(toggle);

    // Autoplay may be blocked by browser policy: stay on the poster, allow manual play.
    var p = video.play();
    if (p && typeof p.catch === 'function') {
      p.catch(function () { syncToggle(); });
    }

    // Don't burn CPU/battery in background tabs.
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) video.pause();
      else if (!userPaused) video.play().catch(function () {});
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
