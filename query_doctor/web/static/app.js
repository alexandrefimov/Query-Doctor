document.addEventListener('DOMContentLoaded', function () {
  function setTheme(theme) {
    var nextTheme = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', nextTheme);
    var toggle = document.getElementById('theme-toggle');
    if (toggle) {
      var dark = nextTheme === 'dark';
      toggle.setAttribute('aria-pressed', dark ? 'true' : 'false');
      toggle.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
      toggle.setAttribute('title', dark ? 'Switch to light theme' : 'Switch to dark theme');
    }
  }
  var themeToggle = document.getElementById('theme-toggle');
  if (themeToggle) {
    setTheme(document.documentElement.getAttribute('data-theme'));
    themeToggle.addEventListener('click', function () {
      var currentTheme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
      var nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
      setTheme(nextTheme);
      try {
        window.localStorage.setItem('query-doctor-theme', nextTheme);
      } catch (error) {
      }
    });
  }
  function setCopyButtonText(button, label, restore) {
    button.textContent = label;
    if (restore) {
      window.setTimeout(function () { button.textContent = 'Copy query'; }, 1400);
    }
  }
  document.addEventListener('click', function (event) {
    var copyButton = event.target.closest && event.target.closest('[data-copy-optimized-query]');
    if (!copyButton) {
      return;
    }
    event.preventDefault();
    var copyBlock = copyButton.closest('[data-optimized-query-block]');
    var code = copyBlock && copyBlock.querySelector('pre code');
    var text = code ? code.textContent : '';
    if (!text) {
      setCopyButtonText(copyButton, 'Nothing to copy', true);
      return;
    }
    function copied() {
      setCopyButtonText(copyButton, 'Copied', true);
    }
    function failed() {
      setCopyButtonText(copyButton, 'Copy failed', true);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(copied).catch(function () {
        fallbackCopyCode(code) ? copied() : failed();
      });
      return;
    }
    fallbackCopyCode(code) ? copied() : failed();
  });
  document.addEventListener('click', function (event) {
    var applyButton = event.target.closest && event.target.closest('[data-action-outcome-show-result]');
    if (!applyButton) {
      return;
    }
    event.preventDefault();
    var card = applyButton.closest('[data-action-outcome-card]');
    var panel = card && card.querySelector('[data-action-outcome-result-panel]');
    if (!panel) {
      return;
    }
    panel.hidden = false;
    var firstButton = panel.querySelector('button');
    if (firstButton) {
      firstButton.focus();
    }
  });
  function rowNavigationTarget(event) {
    if (!event.target.closest) {
      return null;
    }
    if (event.target.closest('a, button, input, select, textarea, summary, form')) {
      return null;
    }
    var row = event.target.closest('[data-href]');
    return row && row.getAttribute('data-href') ? row : null;
  }
  function openRowDetails(row) {
    window.location.assign(row.getAttribute('data-href'));
  }
  document.addEventListener('click', function (event) {
    var row = rowNavigationTarget(event);
    if (row) {
      openRowDetails(row);
    }
  });
  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }
    var row = rowNavigationTarget(event);
    if (row) {
      event.preventDefault();
      openRowDetails(row);
    }
  });
  function openNewScanPanel() {
    var panel = document.getElementById('new-scan');
    if (!panel) {
      return false;
    }
    if (panel.tagName === 'DETAILS') {
      panel.setAttribute('open', '');
    }
    panel.scrollIntoView({block: 'start'});
    var focusTarget = panel.querySelector('select:not([disabled]), input:not([disabled]):not([type="hidden"]), button:not([disabled])');
    if (focusTarget) {
      window.setTimeout(function () { focusTarget.focus(); }, 0);
    }
    return true;
  }
  document.addEventListener('click', function (event) {
    var trigger = event.target.closest && event.target.closest('[data-open-new-scan]');
    if (!trigger) {
      return;
    }
    if (openNewScanPanel()) {
      event.preventDefault();
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, '', '#new-scan');
      }
    }
  });
  if (window.location.hash === '#new-scan') {
    openNewScanPanel();
  }
  function fallbackCopyCode(code) {
    if (!document.createRange || !window.getSelection || !document.execCommand) {
      return false;
    }
    var selection = window.getSelection();
    var range = document.createRange();
    selection.removeAllRanges();
    range.selectNodeContents(code);
    selection.addRange(range);
    var ok = false;
    try {
      ok = document.execCommand('copy');
    } catch (error) {
      ok = false;
    }
    selection.removeAllRanges();
    return ok;
  }
  var form = document.getElementById('analyze-form');
  var pending = document.getElementById('pending-panel');
  if (form) {
    form.addEventListener('submit', function () {
      if (pending) {
        pending.classList.remove('progress-card--hidden');
      }
      var button = form.querySelector('button[type="submit"]');
      if (button) {
        button.disabled = true;
        button.textContent = 'Run';
      }
      var queryInput = form.querySelector('input[name="query_id"]');
      if (queryInput) {
        window.setTimeout(function () { queryInput.value = ''; }, 0);
      }
    });
  }
  Array.prototype.slice.call(document.querySelectorAll('input[data-server-owned-default]')).forEach(function (input) {
    input.value = input.defaultValue || '';
  });
  var infoPopovers = Array.prototype.slice.call(document.querySelectorAll('.info-popover'));
  function closeInfoPopovers(exceptPopover) {
    infoPopovers.forEach(function (popover) {
      if (popover !== exceptPopover) {
        popover.removeAttribute('open');
      }
    });
  }
  infoPopovers.forEach(function (popover) {
    popover.addEventListener('toggle', function () {
      if (popover.open) {
        closeInfoPopovers(popover);
      }
    });
  });
  document.addEventListener('click', function (event) {
    if (!event.target.closest || !event.target.closest('.info-popover')) {
      closeInfoPopovers(null);
    }
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      closeInfoPopovers(null);
    }
  });
  function workflowSelection(root) {
    var selected = root && root.querySelector('input[name="diagnosis_workflow"]:checked');
    return selected ? selected.value : '';
  }
  function syncWorkflowState(root) {
    var workflow = workflowSelection(root);
    if (!workflow) {
      return;
    }
    var diagnosisTarget = workflow === 'query' ? 'query' : 'recent';
    var scanTarget = workflow === 'running' ? 'running' : 'finished';
    Array.prototype.slice.call(root.querySelectorAll('input[name="diagnosis_target"]')).forEach(function (choice) {
      choice.checked = choice.value === diagnosisTarget;
    });
    Array.prototype.slice.call(root.querySelectorAll('input[name="scan_target"][data-scan-target-choice]')).forEach(function (choice) {
      choice.checked = choice.value === scanTarget;
    });
    Array.prototype.slice.call(root.querySelectorAll('input[name="scan_target"][data-scan-target-hidden]')).forEach(function (input) {
      input.value = scanTarget;
    });
  }
  function applyDiagnosisTarget(root) {
    syncWorkflowState(root);
    var target = currentDiagnosisTarget(root);
    Array.prototype.slice.call(root.querySelectorAll('[data-diagnosis-target-field]')).forEach(function (element) {
      var visible = element.getAttribute('data-diagnosis-target-field') === target;
      element.classList.toggle('manual-inputs-hidden', !visible);
    });
    var scanForm = root.querySelector('[data-scan-target-form]');
    if (scanForm) {
      applyScanTarget(scanForm);
      return;
    }
    var scanTarget = currentScanTarget(root);
    updateRecentResultsContext(scanTarget, target);
  }
  Array.prototype.slice.call(document.querySelectorAll('[data-diagnosis-target-root]')).forEach(function (root) {
    applyDiagnosisTarget(root);
    Array.prototype.slice.call(root.querySelectorAll('input[name="diagnosis_workflow"]')).forEach(function (choice) {
      choice.addEventListener('change', function () { applyDiagnosisTarget(root); });
    });
    Array.prototype.slice.call(root.querySelectorAll('input[name="diagnosis_target"]')).forEach(function (choice) {
      choice.addEventListener('change', function () { applyDiagnosisTarget(root); });
    });
  });
  function syncDiagnosisCluster(root) {
    var selector = root.querySelector('[data-diagnosis-cluster-control] select[name="cluster_key"]');
    if (!selector) {
      return;
    }
    Array.prototype.slice.call(root.querySelectorAll('input[type="hidden"][name="cluster_key"]')).forEach(function (input) {
      input.value = selector.value;
    });
  }
  Array.prototype.slice.call(document.querySelectorAll('[data-diagnosis-target-root]')).forEach(function (root) {
    syncDiagnosisCluster(root);
    var selector = root.querySelector('[data-diagnosis-cluster-control] select[name="cluster_key"]');
    if (selector) {
      selector.addEventListener('change', function () { syncDiagnosisCluster(root); });
    }
  });
  function currentDiagnosisTarget(root) {
    var workflow = workflowSelection(root);
    if (workflow) {
      return workflow === 'query' ? 'query' : 'recent';
    }
    var selected = root && root.querySelector('input[name="diagnosis_target"]:checked');
    return selected && selected.value === 'query' ? 'query' : 'recent';
  }
  function currentScanTarget(root) {
    var workflow = workflowSelection(root);
    if (workflow) {
      return workflow === 'running' ? 'running' : 'finished';
    }
    var selected = root && root.querySelector('input[name="scan_target"]:checked');
    if (!selected && root) {
      selected = root.querySelector('input[name="scan_target"][data-scan-target-hidden]');
    }
    return selected && selected.value === 'running' ? 'running' : 'finished';
  }
  function updateRecentResultsContext(scanTarget, diagnosisTarget) {
    var results = document.getElementById('recent-results');
    var heading = results && results.querySelector('.batch-head h1');
    if (!heading) {
      return;
    }
    if (!heading.getAttribute('data-default-title')) {
      heading.setAttribute('data-default-title', heading.textContent || '');
    }
    var defaultTitle = heading.getAttribute('data-default-title') || '';
    if (diagnosisTarget === 'query') {
      heading.textContent = 'Previous Recent Results';
      if (results.tagName === 'DETAILS') {
        results.removeAttribute('open');
        results.setAttribute('data-query-mode-results', 'true');
      }
      return;
    }
    if (results.tagName === 'DETAILS' && results.getAttribute('data-query-mode-results') === 'true') {
      results.setAttribute('open', '');
      results.removeAttribute('data-query-mode-results');
    }
    if (scanTarget === 'running' && defaultTitle === 'Finished Queries') {
      heading.textContent = 'Previous Finished Queries';
      return;
    }
    heading.textContent = defaultTitle;
  }
  function applyScanTarget(form) {
    var root = form.closest('[data-diagnosis-target-root]');
    var target = currentScanTarget(root || form);
    form.setAttribute('action', target === 'running' ? '/running/run' : '/batch/run');
    form.setAttribute('data-active-scan-target', target);
    Array.prototype.slice.call(form.querySelectorAll('input[name="scan_target"][data-scan-target-hidden]')).forEach(function (input) {
      input.value = target;
    });
    Array.prototype.slice.call(form.querySelectorAll('[data-scan-target-field]')).forEach(function (element) {
      var visible = element.getAttribute('data-scan-target-field') === target;
      element.classList.toggle('manual-inputs-hidden', !visible);
    });
    updateRecentResultsContext(target, currentDiagnosisTarget(root));
  }
  function parseScanHourOptions(dateSelect) {
    var raw = dateSelect.getAttribute('data-scan-hour-options') || '{}';
    try {
      return JSON.parse(raw);
    } catch (error) {
      return {};
    }
  }
  function updateScanHourOptions(scanForm) {
    var dateSelect = scanForm.querySelector('select[name="scan_date"][data-scan-hour-options]');
    var hourSelect = scanForm.querySelector('select[name="scan_hour"]');
    if (!dateSelect || !hourSelect) {
      return;
    }
    var optionsByDate = parseScanHourOptions(dateSelect);
    var hourOptions = optionsByDate[dateSelect.value];
    if (!Array.isArray(hourOptions)) {
      return;
    }
    var previousValue = hourSelect.value;
    var hasPreviousValue = false;
    hourSelect.innerHTML = hourOptions.map(function (option) {
      var value = String(option[0]);
      var label = String(option[1]);
      if (value === previousValue) {
        hasPreviousValue = true;
      }
      return '<option value="' + escapeHtml(value) + '">' + escapeHtml(label) + '</option>';
    }).join('');
    if (hasPreviousValue) {
      hourSelect.value = previousValue;
    } else if (hourOptions.length) {
      hourSelect.value = String(hourOptions[hourOptions.length - 1][0]);
    }
  }
  Array.prototype.slice.call(document.querySelectorAll('[data-scan-target-form]')).forEach(function (scanForm) {
    applyScanTarget(scanForm);
    updateScanHourOptions(scanForm);
    Array.prototype.slice.call(scanForm.querySelectorAll('input[name="scan_target"]')).forEach(function (choice) {
      choice.addEventListener('change', function () { applyScanTarget(scanForm); });
    });
    var dateSelect = scanForm.querySelector('select[name="scan_date"][data-scan-hour-options]');
    if (dateSelect) {
      dateSelect.addEventListener('change', function () { updateScanHourOptions(scanForm); });
    }
  });
  function updateRecentWindowWarnings(root) {
    Array.prototype.slice.call((root || document).querySelectorAll('[data-recent-window-field]')).forEach(function (field) {
      var input = field.querySelector('[data-recent-window-input]');
      var warning = field.querySelector('[data-large-window-warning]');
      if (!input || !warning) {
        return;
      }
      var threshold = parseInt(field.getAttribute('data-large-window-threshold') || '1440', 10);
      var value = parseInt(input.value || '0', 10);
      warning.classList.toggle('manual-inputs-hidden', !(value > threshold));
    });
  }
  updateRecentWindowWarnings(document);
  Array.prototype.slice.call(document.querySelectorAll('[data-recent-window-input]')).forEach(function (input) {
    input.addEventListener('input', function () { updateRecentWindowWarnings(document); });
    input.addEventListener('change', function () { updateRecentWindowWarnings(document); });
  });
  function detailJobProgressElements() {
    return Array.prototype.slice.call(document.querySelectorAll('[data-report-job-status-url], [data-optimizer-job-status-url]'));
  }
  function detailJobStatusUrl(progressElement) {
    return progressElement.getAttribute('data-report-job-status-url') || progressElement.getAttribute('data-optimizer-job-status-url');
  }
  function detailJobRedirectUrl(progressElement) {
    return progressElement.getAttribute('data-report-job-url') || progressElement.getAttribute('data-optimizer-job-url');
  }
  function detailJobRedirectTarget(progressElement) {
    var target = detailJobRedirectUrl(progressElement) || window.location.href;
    if (window.location.hash && target.indexOf('#') === -1) {
      target += window.location.hash;
    }
    return target;
  }
  function escapeHtml(value) {
    var htmlEscapes = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'};
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (char) {
      return htmlEscapes[char];
    });
  }
  function safeProgressStepState(value) {
    var state = String(value || 'neutral');
    return ['done', 'running', 'neutral', 'failed', 'skipped'].indexOf(state) >= 0 ? state : 'neutral';
  }
  function renderProgressViewSteps(progressView) {
    if (!progressView || !Array.isArray(progressView.steps)) {
      return '';
    }
    return progressView.steps.map(function (step) {
      var stepState = safeProgressStepState(step && step.state);
      return '<div class="batch-progress-step batch-progress-step--' + stepState + '">'
        + '<strong>' + escapeHtml(step && step.icon) + ' ' + escapeHtml(step && step.label) + '</strong>'
        + '<span>' + escapeHtml(step && step.detail) + '</span></div>';
    }).join('');
  }
  function clampedProgressPercent(value) {
    return String(Math.max(0, Math.min(100, Number(value) || 0))) + '%';
  }
  function applyProgressView(progressElement, progressView, fallbackStage, fallbackProgress) {
    if (!progressElement) {
      return;
    }
    var stageElement = progressElement.querySelector('.progress-stage');
    var fillElement = progressElement.querySelector('.progress-fill');
    var stepsElement = progressElement.querySelector('.batch-progress-steps');
    var nextStage = progressView && progressView.current_stage ? progressView.current_stage : fallbackStage;
    var nextProgress = progressView && typeof progressView.percent === 'number'
      ? progressView.percent
      : fallbackProgress;
    if (stageElement && nextStage != null) {
      stageElement.textContent = String(nextStage);
    }
    if (fillElement) {
      fillElement.style.width = clampedProgressPercent(nextProgress);
    }
    if (stepsElement && progressView && Array.isArray(progressView.steps)) {
      stepsElement.innerHTML = renderProgressViewSteps(progressView);
    }
  }
  function pollDetailJobProgress(progressElement) {
    var statusUrl = detailJobStatusUrl(progressElement);
    if (!statusUrl) {
      return;
    }
    fetch(statusUrl, {cache: 'no-store'})
      .then(function (response) { return response.json(); })
      .then(function (data) {
        applyProgressView(progressElement, data.progress_view, data.stage, data.progress);
        if (data.status === 'ok' || data.status === 'failed' || data.status === 'cancelled') {
          var redirectTarget = detailJobRedirectTarget(progressElement);
          if (new URL(redirectTarget, window.location.href).href === window.location.href) {
            window.location.reload();
          } else {
            window.location.href = redirectTarget;
          }
          return;
        }
        window.setTimeout(function () { pollDetailJobProgress(progressElement); }, 1200);
      })
      .catch(function () { window.setTimeout(function () { pollDetailJobProgress(progressElement); }, 1800); });
  }
  function pollDetailJobProgressElements() {
    detailJobProgressElements().forEach(pollDetailJobProgress);
  }
  var jobPanel = document.querySelector('[data-job-status-url]');
  if (!jobPanel) {
    pollDetailJobProgressElements();
    return;
  }
  var resultSlot = document.getElementById('job-result-slot');
  var errorSlot = document.getElementById('job-error-slot');
  var title = jobPanel.querySelector('.progress-title');
  function runButtonsForJobKind(kind) {
    var selector = '';
    if (kind === 'batch') {
      selector = '#batch-form button[type="submit"]';
    } else if (kind === 'running') {
      selector = '#running-form button[type="submit"]';
    } else if (kind === 'query') {
      selector = '#analyze-form button[type="submit"]';
    }
    return selector ? Array.prototype.slice.call(document.querySelectorAll(selector)) : [];
  }
  function restoreRunButtons(kind) {
    var label = kind === 'query' ? 'Run' : 'Run scan';
    runButtonsForJobKind(kind).forEach(function (button) {
      button.disabled = false;
      button.textContent = label;
    });
  }
  function poll() {
    fetch(jobPanel.getAttribute('data-job-status-url'), {cache: 'no-store'})
      .then(function (response) { return response.json(); })
      .then(function (data) {
        applyProgressView(jobPanel, data.progress_view, data.stage, data.progress);
        var runningProgressSlot = document.getElementById('batch-progress-slot');
        if (runningProgressSlot) { runningProgressSlot.innerHTML = data.progress_html || ''; }
        if (data.status === 'ok') {
          if (title) { title.textContent = 'Analysis complete'; }
          restoreRunButtons(data.kind);
          if (resultSlot && !resultSlot.querySelector('#recent-results')) {
            resultSlot.innerHTML = data.result_html || '';
          }
          return;
        }
        if (data.status === 'failed' || data.status === 'cancelled') {
          if (title) { title.textContent = data.status === 'cancelled' ? 'Analysis stopped' : 'Analysis failed'; }
          restoreRunButtons(data.kind);
          if (errorSlot) {
            errorSlot.hidden = false;
            errorSlot.textContent = data.error || (data.status === 'cancelled' ? 'Job stopped by user.' : 'Analysis failed.');
          }
          return;
        }
        window.setTimeout(poll, 1200);
      })
      .catch(function () { window.setTimeout(poll, 1800); });
  }
  poll();
});
