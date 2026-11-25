const token = document.querySelector('meta[name="session-token"]').content;
const $ = (id) => document.getElementById(id);
const fields = [
  ['provider','ارائه‌دهنده'],['output_dir','پوشهٔ خروجی'],
  ['openai_stt','مدل رونویسی OpenAI'],['openai_translation','مدل ترجمه OpenAI'],['openai_tts','مدل صدا OpenAI'],['openai_voice','گوینده OpenAI'],
  ['openrouter_stt','مدل رونویسی OpenRouter'],['openrouter_translation','مدل ترجمه OpenRouter'],['openrouter_tts','مدل صدا OpenRouter'],['openrouter_voice','گوینده OpenRouter'],
  ['max_minutes','حداکثر مدت (دقیقه)'],['max_height','حداکثر ارتفاع ویدیو'],['max_bytes','حداکثر حجم (بایت)'],['original_audio_percent','درصد صدای اصلی'],
  ['youtube_cookies','مسیر کوکی یوتیوب'],['instagram_cookies','مسیر کوکی اینستاگرام'],['pot_url','نشانی PO Token'],['watermark','متن واترمارک'],
  ['image_model','کد مدل تصویر'],['image_aspect','نسبت تصویر'],['image_reference','مسیر تصویر ورودی'],
  ['caption_model_path','مسیر مدل Whisper'],['caption_fonts_dir','مسیر فونت‌ها'],['caption_language','زبان زیرنویس'],['caption_color','رنگ زیرنویس'],['caption_font','فونت زیرنویس'],['caption_font_size','اندازهٔ فونت']
];
let prefs = {};
async function request(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':token},body:JSON.stringify(data)});
  const result = await response.json(); if (!response.ok) throw new Error(result.error || 'خطا در ارتباط'); return result;
}
function buildSettings() {
  const parent = $('settings-fields'); parent.replaceChildren();
  for (const [name,label] of fields) {
    const box=document.createElement('div'), text=document.createElement('label'), input=document.createElement('input');
    input.id=`setting-${name}`; input.value=prefs[name] || ''; text.htmlFor=input.id; text.textContent=label;
    box.append(text,input); parent.append(box);
  }
}
async function loadSettings() { const result=await request('/api/settings'); prefs=result.preferences; buildSettings(); }
const headings={workspace:['کار جدید','از ایده تا خروجی، همه چیز در یک فضای شخصی.'], models:['مدل‌های محلی','مدل‌های پردازش را روی دستگاه خود مدیریت کنید.'],settings:['تنظیمات','برنامه را مطابق نیاز خود تنظیم کنید.']};
document.querySelectorAll('.nav').forEach(button => button.addEventListener('click',() => {
  document.querySelectorAll('.nav,.page').forEach(el=>el.classList.remove('active')); button.classList.add('active'); $(button.dataset.page).classList.add('active');
  [$('page-title').textContent,$('page-subtitle').textContent]=headings[button.dataset.page];
}));
$('settings-form').addEventListener('submit',async event=>{
  event.preventDefault(); const updated={...prefs}; for (const [name] of fields) updated[name]=$(`setting-${name}`).value.trim();
  try { await request('/api/settings',{preferences:updated,keys:{openai:$('key-openai').value,openrouter:$('key-openrouter').value}}); $('key-openai').value=''; $('key-openrouter').value=''; prefs=updated; $('settings-status').textContent='تنظیمات ذخیره شد.'; }
  catch(e){$('settings-status').textContent=e.message;}
});
async function start(kind,source,target='status') {try{await request('/api/start',{kind,source}); $(target).textContent='در حال آماده‌سازی…'; await refresh();}catch(e){$(target).textContent=e.message;}}
$('start').addEventListener('click',()=>start($('kind').value,$('source').value));
$('download-model').addEventListener('click',()=>start('model',$('model').value,'model-status'));
$('cancel').addEventListener('click',async()=>{try{await request('/api/cancel',{}); $('status').textContent='درخواست لغو ثبت شد؛ منتظر پایان مرحلهٔ جاری بمانید.';}catch(e){$('status').textContent=e.message;}});
let wasRunning=false;
async function refresh(){try{const state=await request('/api/status'); $('status').textContent=state.message; $('model-status').textContent=state.message; $('state-pill').textContent=state.running?'در حال اجرا':'در انتظار'; $('progress-bar').style.width=`${Math.max(0,Math.min(100,state.percent || 0))}%`; $('start').disabled=state.running; $('download-model').disabled=state.running; if(wasRunning&&!state.running) await loadSettings(); wasRunning=state.running;}catch(e){$('status').textContent='ارتباط با برنامه قطع شد.';}}
loadSettings().catch(e=>$('settings-status').textContent=e.message); refresh(); setInterval(refresh,2000);
