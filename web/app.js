const fixtures = [
  {
    id:'newcastle-bournemouth', kickoff:'Sat · 11:30 UTC', home:'Newcastle United', away:'Bournemouth', books:21,
    market:[0.4493,0.2594,0.2913], football1:[0.4710,0.2500,0.2790], elo:[0.489,0.246,0.265], poisson:[0.455,0.267,0.278], odds:[2.18,3.80,3.50]
  },
  {
    id:'brentford-sunderland', kickoff:'Sat · 14:00 UTC', home:'Brentford', away:'Sunderland', books:21,
    market:[0.5768,0.2448,0.1784], football1:[0.5630,0.2460,0.1910], elo:[0.604,0.231,0.165], poisson:[0.548,0.262,0.190], odds:[1.69,4.10,5.90]
  },
  {
    id:'brighton-leeds', kickoff:'Sat · 14:00 UTC', home:'Brighton and Hove Albion', away:'Leeds United', books:21,
    market:[0.4820,0.2692,0.2488], football1:[0.4920,0.2650,0.2430], elo:[0.501,0.259,0.240], poisson:[0.476,0.276,0.248], odds:[2.06,3.65,4.00]
  },
  {
    id:'forest-tottenham', kickoff:'Sat · 14:00 UTC', home:'Nottingham Forest', away:'Tottenham Hotspur', books:21,
    market:[0.3926,0.2809,0.3265], football1:[0.3810,0.2840,0.3350], elo:[0.371,0.271,0.358], poisson:[0.397,0.292,0.311], odds:[2.52,3.55,3.05]
  },
  {
    id:'arsenal-chelsea', kickoff:'Sun · 15:30 UTC', home:'Arsenal', away:'Chelsea', books:20,
    market:[0.5622,0.2473,0.1906], football1:[0.5510,0.2510,0.1980], elo:[0.588,0.232,0.180], poisson:[0.542,0.257,0.201], odds:[1.75,4.00,5.50]
  }
];

let current = fixtures[0];
let selectedOutcome = 0;
const names = ['Home','Draw','Away'];

const pct = n => `${(n*100).toFixed(1)}%`;
const signedPct = n => `${n >= 0 ? '+' : ''}${(n*100).toFixed(1)}%`;
const breakEven = odds => 1/odds;
const ev = (p, odds) => p*odds-1;

function strongestIndex(f){
  return [0,1,2].reduce((best,i)=>ev(f.football1[i],f.odds[i])>ev(f.football1[best],f.odds[best])?i:best,0);
}

function fixtureButton(f){
  const i=strongestIndex(f), value=ev(f.football1[i],f.odds[i]);
  return `<button class="fixture ${f.id===current.id?'active':''}" data-id="${f.id}">
    <div class="fixture-top"><div><strong>${f.home}</strong><span class="away">${f.away}</span></div><span class="ev ${value>=0?'pos':'neg'}">${signedPct(value)}</span></div>
    <div class="fixture-meta"><span>${f.kickoff}</span><span>${names[i]} candidate</span></div>
  </button>`;
}

function renderFixtures(){
  const list=document.getElementById('fixtureList');
  list.innerHTML=fixtures.map(fixtureButton).join('');
  list.querySelectorAll('.fixture').forEach(btn=>btn.addEventListener('click',()=>{
    current=fixtures.find(f=>f.id===btn.dataset.id);
    selectedOutcome=strongestIndex(current);
    render();
  }));
}

function outcomeCard(i){
  const p=current.football1[i], m=current.market[i], price=current.odds[i], value=ev(p,price);
  return `<article class="outcome-card ${i===selectedOutcome?'selected':''}"><button data-outcome="${i}">
    <div class="outcome-title"><span>${names[i]}</span><span class="ev ${value>=0?'pos':'neg'}">EV ${signedPct(value)}</span></div>
    <div class="prob-big">${pct(p)}</div><div class="prob-label">Football 1 preview probability</div>
    <div class="metric-pair"><div class="metric"><span>Market</span><strong>${pct(m)}</strong></div><div class="metric"><span>Best odds</span><strong>${price.toFixed(2)}</strong></div></div>
  </button></article>`;
}

function verdictFor(i){
  const p=current.football1[i], price=current.odds[i], value=ev(p,price);
  const maxP=Math.max(...current.football1);
  const isLikely=p===maxP;
  if(value < -0.02 && isLikely) return {label:'PASS',cls:'pass',title:`Likely winner. Bad price.`,text:`${names[i]} is the strongest football prediction, but ${price.toFixed(2)} requires ${pct(breakEven(price))} just to break even. Football 1's preview estimate is only ${pct(p)}.`};
  if(value >= 0.05) return {label:'CANDIDATE',cls:'candidate',title:`Price deserves attention`,text:`The selection is still uncertain, but the available price implies a lower probability than Football 1's preview estimate. That is a value question, not a claim of certainty.`};
  return {label:'CAUTION',cls:'',title:`Small disagreement, limited margin`,text:`Football 1 and the market are close. The price does not provide enough separation to treat this as a strong value case.`};
}

function renderAnalysis(){
  document.getElementById('kickoffLabel').textContent=current.kickoff;
  document.getElementById('fixtureTitle').innerHTML=`${current.home} <span>vs</span> ${current.away}`;
  document.getElementById('bookmakerLabel').textContent=`${current.books} complete UK books · preview model layer`;
  const outcomes=document.getElementById('outcomeGrid');
  outcomes.innerHTML=[0,1,2].map(outcomeCard).join('');
  outcomes.querySelectorAll('button[data-outcome]').forEach(btn=>btn.addEventListener('click',()=>{selectedOutcome=Number(btn.dataset.outcome);renderAnalysis();}));

  const v=verdictFor(selectedOutcome);
  document.getElementById('realityTitle').textContent=v.title;
  document.getElementById('realityText').textContent=v.text;
  const badge=document.getElementById('decisionBadge'); badge.textContent=v.label; badge.className=`decision ${v.cls}`;

  const i=selectedOutcome;
  const models=[['Market',current.market[i]],['Elo',current.elo[i]],['Poisson',current.poisson[i]],['Football 1',current.football1[i]]];
  document.getElementById('modelRoom').innerHTML=models.map(([label,p])=>`<div class="model-line"><span>${label}</span><div class="bar"><div class="fill" style="width:${Math.min(100,p*100)}%"></div></div><strong>${pct(p)}</strong></div>`).join('');

  const price=current.odds[i], p=current.football1[i], market=current.market[i], value=ev(p,price);
  document.getElementById('priceReality').innerHTML=`
    <div class="price-row"><span>Available price</span><strong>${price.toFixed(2)}</strong></div>
    <div class="price-row"><span>Break-even probability</span><strong>${pct(breakEven(price))}</strong></div>
    <div class="price-row"><span>Football 1 probability</span><strong>${pct(p)}</strong></div>
    <div class="price-row"><span>Model vs market</span><strong>${signedPct(p-market)}</strong></div>
    <div class="price-row"><span>Model-implied EV</span><strong class="ev ${value>=0?'pos':'neg'}">${signedPct(value)}</strong></div>`;

  const team=i===0?current.home:i===2?current.away:'the draw';
  document.getElementById('explanation').textContent=`Football 1 currently puts ${team} at ${pct(p)} in this interface preview. At odds of ${price.toFixed(2)}, the bet needs ${pct(breakEven(price))} to break even. The result may still win or lose; the decision question is whether the price compensates for that uncertainty.`;
}

function render(){ renderFixtures(); renderAnalysis(); }

const tabToPanel={live:'livePanel',reality:'realityPanel',models:'modelsPanel',ledger:'ledgerPanel'};
document.querySelectorAll('.tab').forEach(tab=>tab.addEventListener('click',()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));
  tab.classList.add('active');
  document.getElementById(tabToPanel[tab.dataset.tab]).classList.add('active');
}));

const dialog=document.getElementById('aboutDialog');
document.getElementById('aboutButton').addEventListener('click',()=>dialog.showModal());
document.getElementById('closeDialog').addEventListener('click',()=>dialog.close());

render();
