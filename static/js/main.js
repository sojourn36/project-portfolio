/* 项目作品集 — 交互脚本（无第三方依赖） */
(function () {
  'use strict';

  var header = document.getElementById('siteHeader');
  var navToggle = document.getElementById('navToggle');
  var siteNav = document.getElementById('siteNav');
  var toTop = document.getElementById('toTop');

  /* ---------- 滚动状态 ---------- */
  function onScroll() {
    var y = window.pageYOffset || document.documentElement.scrollTop;
    if (header) header.classList.toggle('is-scrolled', y > 12);
    if (toTop) toTop.classList.toggle('is-visible', y > 520);
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  /* ---------- 移动端菜单 ---------- */
  function closeNav() {
    if (!siteNav || !navToggle) return;
    siteNav.classList.remove('is-open');
    navToggle.setAttribute('aria-expanded', 'false');
  }

  if (navToggle && siteNav) {
    navToggle.addEventListener('click', function () {
      var open = siteNav.classList.toggle('is-open');
      navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });

    // 点击导航链接后自动收起
    siteNav.addEventListener('click', function (event) {
      if (event.target.tagName === 'A') closeNav();
    });

    // 点击外部区域收起
    document.addEventListener('click', function (event) {
      if (!siteNav.classList.contains('is-open')) return;
      if (siteNav.contains(event.target) || navToggle.contains(event.target)) return;
      closeNav();
    });

    // Esc 收起
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') closeNav();
    });

    // 视口变大时重置
    window.addEventListener('resize', function () {
      if (window.innerWidth > 720) closeNav();
    });
  }

  /* ---------- 回到顶部 ---------- */
  if (toTop) {
    toTop.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }
})();
