/* Guest reel: artwork from the Malfoid Artwork Archive (github.com/topovn/malfoid-artwork-archive),
 * shown with the permission of its maintainer, @Topovn. The images and the list are hosted there; this file only
 * reads the archive's public picks list and links every picture to its artist on X.
 * If the archive cannot be reached, the reel stays hidden. */
(function () {
  var BASE = "https://topovn.github.io/malfoid-artwork-archive/";
  var sec = document.getElementById("guest");
  var track = document.getElementById("guest-track");
  if (!sec || !track) return;
  // File names look like <handle>-<tweet id>-<n>.<ext>, the handle being the X account that posted the work.
  var NAME = /^([A-Za-z0-9_]+)-(\d{10,})-\d+\.[A-Za-z0-9]+$/;

  function shuffle(list) {
    for (var i = list.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1)), t = list[i];
      list[i] = list[j];
      list[j] = t;
    }
    return list;
  }

  fetch(BASE + "data/picks.json", { credentials: "omit" })
    .then(function (r) { if (!r.ok) throw new Error("picks " + r.status); return r.json(); })
    .then(function (data) {
      var items = (data.picks || []).map(function (f) {
        var m = NAME.exec(f);
        return m ? { file: f, handle: m[1] } : null;
      }).filter(Boolean);
      if (items.length < 3) return;
      shuffle(items);
      var frag = document.createDocumentFragment();
      // The list is written twice so the CSS scroll can loop seamlessly; the second copy is hidden from keyboard and screen readers.
      [0, 1].forEach(function (copy) {
        items.forEach(function (it) {
          var a = document.createElement("a");
          a.className = "guest-item";
          a.href = "https://x.com/" + encodeURIComponent(it.handle);
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.title = "@" + it.handle + " on X";
          if (copy) { a.tabIndex = -1; a.setAttribute("aria-hidden", "true"); }
          var img = document.createElement("img");
          img.loading = "lazy";
          img.decoding = "async";
          img.alt = "";
          img.src = BASE + "thumbs/" + encodeURIComponent(it.file) + ".webp";
          img.addEventListener("error", function () { a.style.display = "none"; });
          var by = document.createElement("span");
          by.className = "guest-by";
          by.textContent = "@" + it.handle;
          a.appendChild(img);
          a.appendChild(by);
          frag.appendChild(a);
        });
      });
      track.replaceChildren(frag);
      sec.hidden = false;
    })
    .catch(function () { sec.hidden = true; });
})();
