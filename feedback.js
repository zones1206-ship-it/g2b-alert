// Email-only interim intake: no backend, storage, analytics, or automatic send.
document.addEventListener('DOMContentLoaded', () => {
  const dialog = document.getElementById('feedbackDialog');
  const form = document.getElementById('feedbackForm');
  const message = document.getElementById('feedbackMessage');
  const reply = document.getElementById('feedbackReply');
  const category = document.getElementById('feedbackCategory');
  const context = document.getElementById('feedbackNotice');
  const status = document.getElementById('feedbackStatus');
  const text = (ko, en) => document.documentElement.lang === 'en' ? en : ko;
  let notice = null;
  let opener = null;
  // Preserve a separate in-memory draft for each notice. Never persist contact data.
  const drafts = new Map();
  const key = () => notice?.id || '';
  const save = () => drafts.set(key(), {message: message.value, reply: reply.value, category: category.value});

  document.addEventListener('click', event => {
    const button = event.target.closest('[data-feedback-open]');
    if (!button) return;
    opener = button;
    notice = button.dataset.feedbackId ? {id: button.dataset.feedbackId, title: button.dataset.feedbackTitle || ''} : null;
    const draft = drafts.get(key());
    message.value = draft?.message || '';
    reply.value = draft?.reply || '';
    category.value = draft?.category || 'issue';
    context.hidden = !notice;
    context.textContent = notice ? text('관련 공고: ', 'Related notice: ') + notice.title : '';
    status.textContent = '';
    dialog.showModal();
    message.focus();
  });
  document.getElementById('feedbackClose').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => { save(); opener?.focus(); });
  message.addEventListener('input', () => message.setCustomValidity(''));
  function validate() {
    message.setCustomValidity(message.value.trim() ? '' : text('내용을 입력해주세요.', 'Please enter your feedback.'));
    return form.reportValidity();
  }
  function compose() {
    const site = new URL('./', window.location.href);
    site.search = ''; site.hash = '';
    const lines = [category.selectedOptions[0].textContent, '', message.value.trim()];
    if (reply.value.trim()) lines.push('', text('답변 이메일: ', 'Reply email: ') + reply.value.trim());
    if (notice) {
      const link = new URL(site); link.hash = 'n=' + encodeURIComponent(notice.id);
      lines.push('', text('관련 공고: ', 'Related notice: ') + notice.title, link.href);
    }
    lines.push('', site.href);
    return lines.join('\n');
  }
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!validate()) return;
    save();
    const subject = text('[고객 의견] ', '[Feedback] ') + category.selectedOptions[0].textContent;
    window.location.href = 'mailto:zones1206@gmail.com?subject=' + encodeURIComponent(subject) + '&body=' + encodeURIComponent(compose());
    status.textContent = text('아직 전송 완료가 아닙니다. 이메일 앱에서 전송을 눌러주세요. 앱이 열리지 않으면 내용을 복사해 위 주소로 보내주세요.', 'This is not a delivery confirmation. Press Send in your email app. If it does not open, copy the message and email it to the address above.');
  });
  document.getElementById('feedbackCopy').addEventListener('click', async () => {
    if (!validate()) return;
    save();
    try {
      await navigator.clipboard.writeText(compose());
      status.textContent = text('내용을 복사했습니다. 이메일에 붙여넣고 위 주소로 보내주세요.', 'Message copied. Paste it into an email and send it to the address above.');
    } catch {
      message.focus(); message.select();
      status.textContent = text('자동 복사가 차단됐습니다. 선택된 내용을 직접 복사해주세요. 관련 공고 정보는 별도로 함께 적어주세요.', 'Clipboard access was blocked. Copy the selected text manually and include the notice details separately.');
    }
  });
});
