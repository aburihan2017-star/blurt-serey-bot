const fs = require('fs');
const axios = require('axios');
const serey = require('sereyjs');

// ================= কনফিগারেশন =================
const BLURT_USER = 'aburihan1';                             // ব্লার্ট উৎস অ্যাকাউন্ট
const SEREY_USER = process.env.SEREY_USERNAME || 'raihan123'; // সেরি গন্তব্য অ্যাকাউন্ট
const SEREY_POSTING_KEY = process.env.SEREY_POSTING_KEY;      // সেরি পোস্টিং কি

const DATA_FILE = 'automation_data.json';
const MAX_DAILY_POSTS = 2; // দিনে সর্বোচ্চ পোস্ট
const DAY_IN_MS = 86400 * 1000;

const SEREY_CHAIN_ID = '5205c25d3e87cb3e8e527e6fbbf324b7b2b9fe7a7192c604ce5b174d08987324';
const SEREY_PREFIX = 'SRY';

// সেরি চেইন কনফিগ
serey.config.set('address_prefix', SEREY_PREFIX);
serey.config.set('chain_id', SEREY_CHAIN_ID);

const BLURT_NODES = [
  'https://blurt-rpc.saboin.com',
  'https://rpc.blurt.one',
  'https://blurt.world',
];

// বডি থেকে ইমেজ/থাম্বনেইল বের করার ফাংশন
function extractImagesFromBody(body) {
  if (!body) return [];
  const imgRegex = /https?:\/\/[^\s"'<>]+\.(?:jpg|jpeg|gif|png|webp)/gi;
  const matches = body.match(imgRegex);
  return matches ? Array.from(new Set(matches)) : [];
}

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

// শুধুমাত্র নিজের মূল পোস্টগুলো সংগ্রহ করা (কমেন্ট বা রিব্লগ বাদ দিয়ে)
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
      // ফিল্টার: রিব্লগ নয়, কমেন্ট নয়, এবং টাইটেল ও পর্যাপ্ত লেখা আছে
      const isOriginal = p.author === BLURT_USER;
      const isRootPost = !p.parent_author || p.parent_author === '';
      const hasContent = p.title && p.title.trim().length > 0 && p.body && p.body.trim().length > 50;
      const notPosted = !postedSet.has(p.permlink);

      if (isOriginal && isRootPost && hasContent && notPosted) {
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

async function sendSereyHttpRpc(api, method, params = []) {
  const payload = {
    jsonrpc: '2.0',
    method: 'call',
    params: [api, method, params],
    id: 1,
  };

  const res = await axios.post('https://api.serey.io', payload, {
    headers: {
      'Content-Type': 'application/json',
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    },
    timeout: 20000,
  });

  if (res.data && res.data.error) {
    throw new Error(JSON.stringify(res.data.error));
  }
  return res.data ? res.data.result : null;
}

// সেরি বাংলা কমিউনিটিতে পোস্ট ব্রডকাস্ট
async function postToSereyNative(title, body, permlink) {
  try {
    console.log('📡 সেরি ব্লকচেইন নোড থেকে বর্তমান ব্লক ডাটা সংগ্রহ করা হচ্ছে...');

    const dgp = await sendSereyHttpRpc('database_api', 'get_dynamic_global_properties', []);
    
    const headBlockNumber = dgp.head_block_number;
    const headBlockId = dgp.head_block_id;

    const refBlockNum = headBlockNumber & 0xffff;
    const refBlockPrefix = Buffer.from(headBlockId, 'hex').readUInt32LE(4);

    const blockTime = new Date(dgp.time + 'Z').getTime();
    const expiration = new Date(blockTime + 60000).toISOString().split('.')[0];

    // থাম্বনেইল হিসেবে ছবি সংগ্রহ
    const images = extractImagesFromBody(body);

    const metadata = {
      tags: ['bengali-community', 'blurt', 'blog'],
      image: images.slice(0, 5),
      app: 'serey/2.0',
      format: 'markdown'
    };

    const commentOp = [
      'comment',
      {
        parent_author: '',
        parent_permlink: 'bengali-community',
        author: SEREY_USER,
        permlink: permlink,
        title: title,
        body: body,
        json_metadata: JSON.stringify(metadata),
      },
    ];

    const tx = {
      ref_block_num: refBlockNum,
      ref_block_prefix: refBlockPrefix,
      expiration: expiration,
      operations: [commentOp],
      extensions: [],
    };

    console.log(`🔑 ট্রানজাকশন সাইন করা হচ্ছে...`);
    const signedTx = serey.auth.signTransaction(tx, [SEREY_POSTING_KEY]);

    console.log(`🚀 সেরি বাংলা কমিউনিটিতে ব্রডকাস্ট করা হচ্ছে: "${title}"`);
    console.log(`📌 Permlink: ${permlink}`);
    console.log(`🖼️ থাম্বনেইল ছবি পাওয়া গেছে: ${images.length} টি`);

    try {
      const res = await sendSereyHttpRpc('network_broadcast_api', 'broadcast_transaction_synchronous', [signedTx]);
      console.log(`🎉 সিনক্রোনাস ব্রডকাস্ট সফল:`, JSON.stringify(res));
    } catch (e) {
      const res2 = await sendSereyHttpRpc('network_broadcast_api', 'broadcast_transaction', [signedTx]);
      console.log(`🎉 ব্রডকাস্ট সম্পন্ন:`, JSON.stringify(res2));
    }

    try {
      await axios.get(`https://global-api.serey.io/api/v2/serey-web/list-by-author?author=${SEREY_USER}&limit=5&offset=0`, { timeout: 10000 });
    } catch (e) {}

    return true;
  } catch (err) {
    console.error('❌ ব্রডকাস্ট এরর:', err.message);
    return false;
  }
}

async function main() {
  console.log('🤖 বট চালু হচ্ছে...');
  if (!SEREY_POSTING_KEY) {
    console.error('❌ ত্রুটি: SEREY_POSTING_KEY পাওয়া যায়নি! GitHub Secrets চেক করুন।');
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

  // কিউ খালি থাকলে নতুন করে ব্লার্টের ১ বছর আগের পোস্ট সংগ্রহ
  if (!data.queue || data.queue.length === 0) {
    console.log(`ব্লার্ট অ্যাকাউন্ট (@${BLURT_USER}) থেকে ১ বছর আগের আসল ব্লগ পোস্ট আনা হচ্ছে...`);
    const fetched = await fetchOneYearOldPosts(postedSet);
    data.queue = fetched;
    saveData(data);
  }

  if (!data.queue || data.queue.length === 0) {
    console.log('পোস্ট করার মতো কোনো নতুন পোস্ট পাওয়া যায়নি।');
    return;
  }

  // লুপ চালিয়ে নিশ্চিত করা যে খালি কোনো পোস্ট চেইনে যাবে না
  let postSelected = null;
  while (data.queue.length > 0) {
    const item = data.queue.shift();
    let title = typeof item === 'object' ? item.title : null;
    let body = typeof item === 'object' ? item.body : null;
    let permlinkKey = typeof item === 'object' ? item.permlink : item;

    // যদি অবজেক্টে বডি না থাকে তবে ব্লার্ট থেকে এনে দেখা
    if (!title || !body) {
      const details = await getPostDetails(permlinkKey);
      if (details && details.author === BLURT_USER && !details.parent_author && details.title && details.body) {
        title = details.title.trim();
        body = details.body.trim();
      }
    }

    // চূড়ান্ত যাচাই: টাইটেল ও পর্যাপ্ত বডি আছে কিনা
    if (title && body && body.length > 50) {
      postSelected = { title, body, permlinkKey };
      break;
    } else {
      console.log(`⏩ কমেন্ট বা রিব্লগ পোস্ট হওয়ায় বাদ দেওয়া হলো: ${permlinkKey}`);
      data.posted = data.posted || [];
      data.posted.push(permlinkKey);
    }
  }

  if (!postSelected) {
    console.log('বৈধ কোনো পোস্ট পাওয়া যায়নি।');
    saveData(data);
    return;
  }

  const { title, body, permlinkKey } = postSelected;

  console.log(`\n📄 নির্বাচিত পোস্ট: "${title}"`);
  console.log(`📊 পোস্টের লেখার পরিমাণ: ${body.length} ক্যারেক্টার`);

  // ইউনিক পার্মালিঙ্ক তৈরি
  const cleanTitle = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const sereyPermlink = `${cleanTitle.slice(0, 35)}-${Date.now().toString(36)}`;

  const success = await postToSereyNative(title, body, sereyPermlink);

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
  console.log('\n✨ প্রক্রিয়া সফলভাবে সম্পন্ন হয়েছে।');
}

main();
