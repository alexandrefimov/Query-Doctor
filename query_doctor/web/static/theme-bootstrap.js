(function () {
  try {
    var storedTheme = window.localStorage.getItem('query-doctor-theme');
    var systemTheme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    var theme = storedTheme === 'dark' || storedTheme === 'light' ? storedTheme : systemTheme;
    document.documentElement.setAttribute('data-theme', theme);
    var storedDesign = window.localStorage.getItem('query-doctor-design');
    var designOrder = ['serious', 'command'];
    var design = designOrder.indexOf(storedDesign) >= 0 ? storedDesign : 'serious';
    document.documentElement.setAttribute('data-design', design);
  } catch (error) {
    document.documentElement.setAttribute('data-theme', 'light');
    document.documentElement.setAttribute('data-design', 'serious');
  }
})();
