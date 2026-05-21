(function () {
  try {
    var storedTheme = window.localStorage.getItem('query-doctor-theme');
    var systemTheme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    var theme = storedTheme === 'dark' || storedTheme === 'light' ? storedTheme : systemTheme;
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.setAttribute('data-design', 'serious');
  } catch (error) {
    document.documentElement.setAttribute('data-theme', 'light');
    document.documentElement.setAttribute('data-design', 'serious');
  }
})();
