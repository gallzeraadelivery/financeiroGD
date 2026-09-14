document.querySelectorAll('form[data-confirm]').forEach(form=>form.addEventListener('submit',event=>{if(!confirm(form.dataset.confirm))event.preventDefault();}));
document.querySelector('.mobile-menu')?.addEventListener('click',event=>{const opened=document.body.classList.toggle('menu-open');event.currentTarget.setAttribute('aria-expanded',String(opened));});
const prices=document.getElementById('product-prices');
if(prices){const values=JSON.parse(prices.textContent);document.getElementById('id_product')?.addEventListener('change',event=>{document.getElementById('id_unit_price').value=values[event.target.value]||'';});}
