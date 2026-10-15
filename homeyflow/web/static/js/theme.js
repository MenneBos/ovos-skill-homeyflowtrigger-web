// Thema vóór het tekenen van de pagina instellen (voorkomt flitsen).
(function () {
  var theme = 'dark';
  try {
    var saved = localStorage.getItem('hf-theme');
    if (saved === 'light' || saved === 'dark') theme = saved;
  } catch (e) { /* opslag niet beschikbaar: standaardthema */ }
  document.documentElement.setAttribute('data-theme', theme);
})();
