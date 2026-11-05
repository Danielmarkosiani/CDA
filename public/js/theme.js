// თემის არჩევა გვერდის ჩატვირთვამდე (ციმციმის თავიდან ასაცილებლად). ნაგულისხმევი: ღია
(function () {
  var t = null;
  try { t = localStorage.getItem('cda-theme'); } catch (e) {}
  if (t !== 'dark' && t !== 'light') t = 'light';
  document.documentElement.setAttribute('data-theme', t);
})();
