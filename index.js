const fs = require('fs');
const axios = require('axios');
const puppeteer = require('puppeteer');

// ================= কনফিগারেশন =================
const BLURT_USER = 'aburihan1';                                                     // ব্লার্ট অ্যাকাউন্ট
const SEREY_USER = process.env.SEREY_USERNAME || 'raihan123';                         // সেরি ইউজার
const SEREY_PASS = process.env.SEREY_PASSWORD || process.env.SEREY_POSTING_KEY;      // সেরি পোস্টিং কি / পাসওয়ার্ড

const DATA_FILE = 'automation_data.json';
const MAX_DAILY_POSTS = 2;
const DAY_IN_MS = 86400 * 1000;

const BLURT_NODES = [
  'https://blurt-rpc.saboin.com',
  'https://rpc.blurt.one',
  'https://blurt.world',
];

async function blurtCall(method, params) {
  const payload = { jsonrpc: '2.0', method, params, id: 1 };
  for (const node of BLURT_NODES) {
    try {
      const res = await axios.post(node, payload, { timeout: 12000 });
      if (res.data && res.data.result) return res.data.result;
    } catch (e) {
      continue;
    }
  }
  return null;
}

function loadData() {
  if (fs.existsSync(DATA_FILE)) {
    try {
      return JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
    } catch (e) {}
  }
  return { queue: [], posted: [], timestamps: [] };
}

function saveData(data) {
  fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2));
}

// শুধুমাত্র নিজের মূল পোস্ট সংগ্রহ
async function fetchOneYearOldPosts(postedSet) {
  const oneYearAgo = new Date(Date.now() - 365 * DAY_IN_MS);
  const beforeDate = oneYearAgo.toISOString().split('.')[0];
  
  const posts = await blurtCall('condenser_api.get_discussions_by_author_before_date', [
    BLURT_USER,
    '',
    beforeDate,
    100,
  ]);

  if (posts && Array.isArray(posts)) {
    const list = [];
    for (const p of posts.reverse()) {
      const isOriginal = p.author === BLURT_USER;
      const isRoot = !p.parent_author || p.parent_author === '';
      const hasContent = p.title && p.title.trim().length > 0 && p.body && p.body.trim().length > 50;
      const notPosted = !postedSet.has(p.permlink);

      if (isOriginal && isRoot && hasContent && notPosted) {
        list.push({
          permlink: p.permlink,
          title: p.title.trim(),
          body: p.body.trim()
        });
      }
    }
    return list;
  }
  return [];
}

async function getPostDetails(permlink) {
  return blurtCall('condenser_api.get_content', [BLURT_USER, permlink]);
}

/**
 * Puppeteer দিয়ে ওয়েবসাইটে স্বয়ংক্রিয়ভাবে পোস্ট করা
 */
async function postViaSereyBrowser(title, body) {
  console.log('🌐 হেডলেস ক্রোম ব্রাউজার চালু হচ্ছে...');
  
  const browser = await puppeteer.launch({
    headless: 'new',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--no-zygote',
      '--single-process'
    ]
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36');
  await page.setViewport({ width: 1366, height: 768 });

  try {
    // ১. ওয়েবসাইটে ঢুকে লগইন করা
    console.log('🔗 Serey ওয়েবসাইটে প্রবেশ করা হচ্ছে...');
    await page.goto('https://serey.io', { waitUntil: 'networkidle2', timeout: 60000 });

    console.log('🔑 লগইন পপ-আপ খোলা হচ্ছে...');
    const loginLink = await page.waitForSelector('text/Sign up / Log in, text/Log in', { timeout: 15000 }).catch(() => null);
    if (loginLink) {
      await loginLink.click();
    } else {
      await page.goto('https://serey.io/login', { waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {});
    }

    // ইউজারনেম ও পোস্টিং কি ইনপুট
    console.log('✍️ ইউজারনেম ও কি (Key) প্রবেশ করানো হচ্ছে...');
    await page.waitForSelector('input[type="text"], input[name="username"]', { timeout: 15000 });
    await page.type('input[type="text"], input[name="username"]', SEREY_USER, { delay: 40 });
    await page.type('input[type="password"]', SEREY_PASS, { delay: 40 });

    const submitBtn = await page.$('button[type="submit"]') || await page.$('text/Login');
    if (submitBtn) await submitBtn.click();
    
    await new Promise(r => setTimeout(r, 6000));

    // ২. Create Post পেজে যাওয়া
    console.log('📝 "Write a Blog Post" পেজে প্রবেশ করা হচ্ছে...');
    await page.goto('https://serey.io/create-post', { waitUntil: 'networkidle2', timeout: 40000 });
    await new Promise(r => setTimeout(r, 4000));

    // ৩. Title ফিল্ড পূরণ
    console.log(`✍️ টাইটেল লেখা হচ্ছে: "${title}"`);
    const titleInput = await page.waitForSelector('input[placeholder*="Title"], input[maxlength="255"], textarea[placeholder*="Title"]', { timeout: 15000 });
    await titleInput.click({ clickCount: 3 });
    await titleInput.type(title, { delay: 25 });

    // ৪. Content ফিল্ডে মূল ব্লগ বডি পেস্ট করা
    console.log(`📄 ব্লগের লেখা পেস্ট করা হচ্ছে (${body.length} ক্যারেক্টার)...`);
    const editor = await page.$('textarea[name="body"]') || await page.$('.ql-editor') || await page.$('div[contenteditable="true"]');
    if (editor) {
      await editor.focus();
      await page.evaluate((el, text) => {
        if (el.tagName === 'TEXTAREA') {
          el.value = text;
          el.dispatchEvent(new Event('input', { bubbles: true }));
        } else {
          el.innerText = text;
          el.dispatchEvent(new Event('input', { bubbles: true }));
        }
      }, editor, body);
    }
    await new Promise(r => setTimeout(r, 3000));

    // ৫. নিচের পাবলিশ বাটনে ক্লিক (ক্যাটাগরি মোডাল আনার জন্য)
    console.log('🔘 ক্যাটাগরি পপ-আপ আনার জন্য বাটনে ক্লিক করা হচ্ছে...');
    const initialPublishBtn = await page.$('button[type="submit"]') || await page.$('text/Publish') || await page.$('text/Post');
    if (initialPublishBtn) {
      await initialPublishBtn.click();
    }
    await new Promise(r => setTimeout(r, 3000));

    // ৬. "Your post belongs to category:" পপ-আপে নীল Publish বাটনে ক্লিক
    console.log('🔍 ক্যাটাগরি পপ-আপের জন্য অপেক্ষা করা হচ্ছে...');
    const modalCategory = await page.waitForSelector('text/Your post belongs to category:', { timeout: 10000 }).catch(() => null);
    
    if (modalCategory) {
      console.log('✅ ক্যাটাগরি পপ-আপ পাওয়া গেছে!');
      console.log('🚀 পপ-আপের নীল "Publish" বাটনে ক্লিক করা হচ্ছে...');
      const finalPublishBtn = await page.evaluateHandle(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        return buttons.find(b => b.textContent.trim() === 'Publish');
      });

      if (finalPublishBtn) {
        await finalPublishBtn.click();
        console.log('⏳ পোস্ট সম্পূর্ণ সাবমিট হওয়ার জন্য অপেক্ষা করা হচ্ছে...');
        await new Promise(r => setTimeout(r, 12000));
      }
    } else {
      console.log('⚠️ সরাসরি সাবমিট হতে পারে, ৮ সেকেন্ড অপেক্ষা...');
      await new Promise(r => setTimeout(r, 8000));
    }

    console.log('🎉 পোস্ট সফলভাবে ওয়েবসাইটে পাবলিশ হয়েছে!');
    await browser.close();
    return true;

  } catch (err) {
    console.error('❌ ব্রাউজার অটোমেশন এরর:', err.message);
    await browser.close();
    return false;
  }
}

async function main() {
  console.log('🤖 Puppeteer ব্রাউজার বট চালু হচ্ছে...');
  if (!SEREY_PASS) {
    console.error('❌ ত্রুটি: SEREY_POSTING_KEY বা SEREY_PASSWORD পাওয়া যায়নি! GitHub Secrets চেক করুন।');
    return;
  }

  const data = loadData();
  const now = Date.now();

  data.timestamps = (data.timestamps || []).filter(t => now - t < DAY_IN_MS);
  if (data.timestamps.length >= MAX_DAILY_POSTS) {
    console.log(`আজকের দৈনিক সীমা (${MAX_DAILY_POSTS} টি পোস্ট) পূর্ণ হয়েছে।`);
    return;
  }

  const postedSet = new Set(data.posted || []);

  if (!data.queue || data.queue.length === 0) {
    console.log(`ব্লার্ট (@${BLURT_USER}) থেকে পোস্ট আনা হচ্ছে...`);
    const fetched = await fetchOneYearOldPosts(postedSet);
    data.queue = fetched;
    saveData(data);
  }

  let postSelected = null;
  while (data.queue.length > 0) {
    const item = data.queue.shift();
    let title = typeof item === 'object' ? item.title : null;
    let body = typeof item === 'object' ? item.body : null;
    let permlinkKey = typeof item === 'object' ? item.permlink : item;

    if (!title || !body) {
      const details = await getPostDetails(permlinkKey);
      if (details && details.author === BLURT_USER && details.title && details.body) {
        title = details.title.trim();
        body = details.body.trim();
      }
    }

    if (title && body && body.length > 50) {
      postSelected = { title, body, permlinkKey };
      break;
    } else {
      data.posted = data.posted || [];
      data.posted.push(permlinkKey);
    }
  }

  if (!postSelected) {
    console.log('কোনো বৈধ পোস্ট পাওয়া যায়নি।');
    saveData(data);
    return;
  }

  const { title, body, permlinkKey } = postSelected;
  const success = await postViaSereyBrowser(title, body);

  if (success) {
    data.posted = data.posted || [];
    data.posted.push(permlinkKey);
    data.timestamps = data.timestamps || [];
    data.timestamps.push(now);
    console.log('✅ ডাটা সেভ করা হয়েছে।');
  } else {
    data.queue.unshift(postSelected);
  }

  saveData(data);
  console.log('\n✨ সম্পূর্ণ প্রক্রিয়া সফলভাবে সম্পন্ন হয়েছে।');
}

main();
