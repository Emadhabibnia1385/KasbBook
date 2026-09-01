/* Send a Persian-speaking first-time visitor to the Persian site.
 *
 * Browser language, not location. A Persian speaker in Berlin should get
 * Persian, and somebody in Tehran who reads English documentation all day
 * should not be dragged out of it — the browser's own setting knows which, and
 * an IP address does not.
 *
 * It runs once ever. After the first visit a flag says the question has been
 * answered, so a reader who lands on Persian and switches to English with the
 * header's own control stays in English from then on. Without that, the guess
 * would undo their choice on every page they opened.
 *
 * The destination is read from the alternate link the page already carries
 * rather than assembled from a base path. An assembled one was wrong the first
 * time it was tried anywhere but production, and following the site's own link
 * cannot drift from where the site actually is.
 *
 * Storage throws in a private window or with site data blocked. Every path
 * treats that as "do nothing", because a redirect that cannot remember itself
 * is a redirect that loops.
 */
(function () {
  var ASKED = "kasbbook.language.asked";

  try {
    if (localStorage.getItem(ASKED)) return;
    localStorage.setItem(ASKED, "1");
  } catch (e) {
    return;
  }

  if (document.documentElement.lang === "fa") return;

  var langs = navigator.languages || [navigator.language || ""];
  var persian = langs.some(function (tag) { return /^(fa|pes|prs)\b/i.test(tag); });
  if (!persian) return;

  // Material renders one of these per language, pointing at this same page in
  // that language. That is exactly the destination, already computed.
  var link = document.querySelector('link[rel="alternate"][hreflang="fa"]');
  if (link && link.href) window.location.replace(link.href);
})();
