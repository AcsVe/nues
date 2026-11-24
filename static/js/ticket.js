/* التأكيد الرسمي: يرسم رمز QR لرابط التحقق ويطبع الصفحة. */
(function () {
  'use strict';
  var box = document.getElementById('qr');
  if (box && window.qrcode) {
    var q = window.qrcode(0, 'M');
    q.addData(location.origin + box.dataset.url);
    q.make();
    box.innerHTML = q.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
  }
  var p = document.getElementById('tkPrint');
  if (p) p.addEventListener('click', function () { window.print(); });
})();
