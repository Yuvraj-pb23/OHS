 document.addEventListener("DOMContentLoaded", function() {
    let currentPage = window.location.pathname.split("/").pop();
    document.querySelectorAll(".nav-link").forEach(link => {
      if(link.getAttribute("href") === currentPage) {
        link.classList.add("active");
      }
    });
  });
  const hamburger = document.getElementById("hamburger");
const navLinks = document.getElementById("navLinks");

hamburger.addEventListener("click", () => {
  hamburger.classList.toggle("active");
  navLinks.classList.toggle("show");
}); 


  const currentPage = window.location.pathname.split("/").pop();
  document.querySelectorAll(".navbar a").forEach(link => {
    if(link.getAttribute("href") === currentPage) {
      link.classList.add("active");
    }
  });
  