(function(){
  var store={get:function(k){try{return localStorage.getItem(k)}catch(e){return null}},
             set:function(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
  document.querySelectorAll('[data-toggle]').forEach(function(box){
    var cls=box.getAttribute('data-toggle'), saved=store.get('lf-'+cls);
    if(saved!==null) box.checked = saved==='1';
    var apply=function(){document.body.classList.toggle(cls, box.checked); store.set('lf-'+cls, box.checked?'1':'0');};
    box.addEventListener('change', apply); apply();
  });
  var f=document.getElementById('filter');
  if(f){f.addEventListener('input',function(){var q=f.value.toLowerCase();
    document.querySelectorAll('table.abbr tbody tr').forEach(function(tr){
      tr.style.display = tr.textContent.toLowerCase().indexOf(q)>=0 ? '' : 'none';});});}
})();
