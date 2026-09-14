const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
  const browser = await chromium.launch({headless:true,channel:'msedge'});
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('https://financeiro.gdapps.online/login/',{waitUntil:'networkidle'});
  await page.screenshot({path:'.private/login.png',fullPage:true});
  await page.locator('#email').fill('dimymgalvan@gmail.com');
  await page.locator('#password').fill(fs.readFileSync('.private/initial-password','utf8').trim());
  await page.getByRole('button',{name:'Entrar na minha conta'}).click();
  await page.waitForURL('https://financeiro.gdapps.online/');
  await page.screenshot({path:'.private/dashboard.png',fullPage:true});
  for (const [url,title] of [['/contas/payable/','Contas a pagar'],['/contas/receivable/','Contas a receber'],['/vendas/nova/','Nova venda parcelada'],['/usuarios/novo/','Novo usuário'],['/lembretes/','Um aviso na hora certa']]){
    const response=await page.goto('https://financeiro.gdapps.online'+url,{waitUntil:'networkidle'});
    if(response.status()!==200)throw new Error(url+': '+response.status());
    await page.getByRole('heading',{name:title,exact:false}).waitFor();
  }
  await page.setViewportSize({width:390,height:844});
  await page.goto('https://financeiro.gdapps.online/',{waitUntil:'networkidle'});
  await page.screenshot({path:'.private/mobile.png',fullPage:true});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
  if(overflow)throw new Error('Horizontal overflow on mobile');
  await page.getByRole('button',{name:'Abrir menu'}).click();
  await page.getByRole('link',{name:'Contas a pagar',exact:false}).click();
  await page.waitForURL('**/contas/payable/');
  if(errors.length)throw new Error(errors.join('\n'));
  console.log('Browser QA: login, dashboard, forms, permissions screen, reminders and mobile passed.');
  await browser.close();
})().catch(e=>{console.error(e.message);process.exit(1)});
