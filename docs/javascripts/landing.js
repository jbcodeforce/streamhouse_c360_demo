/* Landing page tiles: double click anywhere on a tile follows its "Explore" link.
   One delegated listener on the document, so it survives instant navigation. */
document.addEventListener("dblclick", function (event) {
  var tile = event.target.closest(".sh-tiles li");
  if (!tile) {
    return;
  }
  var link = tile.querySelector("a[href]");
  if (link) {
    link.click();
  }
});
