const fs = require('fs');
const axios = require('axios');
const serey = require('sereyjs');

// ================= কনফিগারেশন =================
const BLURT_USER = 'aburihan1'; // যে ব্লার্ট অ্যাকাউন্ট থেকে পোস্ট আনা হবে
const SEREY_USER = process.env.SEREY_USERNAME || 'raihan123'; // সেরি ইউজার
const SEREY_POSTING_KEY = process.env.SEREY_POSTING_KEY; // সেরি পোস্টিং প্রাইভেট কি

const DATA_FILE = 'automation_data.json';
const MAX_DAILY_POSTS = 2; // প্রতিদিন সর্বোচ্চ পোস্টের সংখ্যা
const DAY_IN_MS = 86400 * 1000;

const SEREY_CHAIN_ID = '5205c25d3e87cb3e8e527e6fbbf324b7b2b9fe7a7192c604ce5b174d08987324';
const SEREY_PREFIX = 'SRY';

// সেরি চেইন কনফিগারেশন
serey.config.set('address_prefix', SEREY_PREFIX);
serey.config.set('chain_id', SEREY_CHAIN_ID);

const BLURT_NODES = [
  'https://blurt-rpc.saboin.com',
  'https://rpc.blurt.one',
  'https://blurt.world',
];

// বডি থেকে ইমেজ / থাম্বনেইল URL বের করার ফাংশন
function extractImagesFromBody(body) {
  const imgRegex = /https?:\/\/[^\s"'<>]+\.(?:jpg|jpeg|gif|png|webp)/gi;
  const matches = body.match(imgRegex);
  return matches ? Array.from(new Set(matches)) : [];
}

async function blurtCall(method, params) {
  const payload = { jsonrpc: '2.0', method, params, id: 1 };
  for (const node of BLURT_NODES) {
    try {
      const res = await axios.post(node, payload, { timeout: 10000 });
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

async function fetchOneYearOldPosts(postedSet) {
  const oneYearAgo = new Date(Date.now() - 365 * DAY_IN_MS);
  const beforeDate = oneYearAgo.toISOString().split('.')[0];
  const posts = await blurtCall('condenser_api.get_discussions_by_author_before_date', [
    BLURT_USER,
    '',
    beforeDate,
    100,
  ]);
  if (posts) {
    const list = [];
    for (const p of posts.reverse()) {
      if (p.permlink && !postedSet.has(p.permlink)) {
        list.push(p.permlink);
      }
    }
    return list;
  }
  return [];
}

async function getPostDetails(permlink) {
  return blurtCall('condenser_api.get_content', [BLURT_USER, permlink]);
}

// সেরি ব্লকচেইন RPC কল
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

// সেরি বাংলা কমিউনিটিতে ব্রডকাস্ট ফাংশন
async function postToSereyNative(title, body, permlink) {
  try {
    console.log('📡 সেরি ব্লকচেইন নোড থেকে বর্তমান ব্লক ডাটা সংগ্রহ করা হচ্ছে...');

    const dgp = await sendSereyHttpRpc('database_api', 'get_dynamic_global_properties', []);
    
    const headBlockNumber = dgp.head_block_number;
    const headBlockId = dgp.head_block_id;

    // TaPoS ব্লকচেইন হিসাব
    const refBlockNum = headBlockNumber & 0xffff;
    const refBlockPrefix = Buffer.from(headBlockId, 'hex').readUInt32LE(4);

    // টাইমস্ট্যাম্প
    const blockTime = new Date(dgp.time + 'Z').getTime();
    const expiration = new Date(blockTime + 60000).toISOString().split('.')[0];

    // পোস্টের মূল ছবিগুলো (থাম্বনেইল হিসেবে ব্যবহারের জন্য)
    const images = extractImagesFromBody(body);

    // মেটাডাটা তৈরি (যা ফ্রন্টএন্ডে ইমেজ ও ট্যাগ দেখানোর জন্য জরুরি)
    const metadata = {
      tags: ['bengali-community', 'blurt', 'blog'],
      image: images.slice(0, 5), // থাম্বনেইল হিসেবে প্রথম ছবিগুলো
      app: 'serey/2.0',
      format: 'markdown'
    };

    // কমেন্ট অপারেশন (মূল পোস্ট তৈরি)
    const commentOp = [
      'comment',
      {
        parent_author: '',
        parent_permlink: 'bengali-community', // বাংলা কমিউনিটি
        author: SEREY_USER,                   // raihan123
        permlink: permlink,
        title: title,
        body: body,                           // নিখুঁত মার্কডাউন ফরম্যাট
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

    console.log(`🚀 সেরি বাংলা কমিউনিটিতে ব্রডকাস্ট করা হচ্ছে: ${title}`);
    console.log(`📌 Permlink: ${permlink}`);

    try {
      const res = await sendSereyHttpRpc('network_broadcast_api', 'broadcast_transaction_synchronous', [signedTx]);
      console.log(`🎉 সিনক্রোনাস ব্রডকাস্ট সফল:`, JSON.stringify(res));
    } catch (e) {
      const res2 = await sendSereyHttpRpc('network_broadcast_api', 'broadcast_transaction', [signedTx]);
      console.log(`🎉 ব্রডকাস্ট সম্পন্ন:`, JSON.stringify(res2));
    }

    // সেরি ফ্রন্টএন্ড ক্যাশ রিফ্রেশ পিং
    try {
      await axios.get(`https://global-api.serey.io/api/v2/serey-web/list-by-author?author=${SEREY_USER}&limit=5&offset=0`, { timeout: 10000 });
    } catch (e) {}

    return true;
  } catch (err) {
    console.error('❌ ব্রডকাস্ট এরর:', err.message);
    return false;
  }
}

// মূল এক্সিকিউশন
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

  if (!data.queue || data.queue.length === 0) {
    console.log(`ব্লার্ট অ্যাকাউন্ট (@${BLURT_USER}) থেকে ১ বছর আগের পোস্ট আনা হচ্ছে...`);
    const fetched = await fetchOneYearOldPosts(postedSet);
    data.queue = fetched;
    saveData(data);
  }

  if (!data.queue || data.queue.length === 0) {
    console.log('পোস্ট করার মতো কোনো নতুন পোস্ট পাওয়া যায়নি।');
    return;
  }

  const permlinkToPost = data.queue.shift();
  const postInfo = await getPostDetails(permlinkToPost);

  if (!postInfo || !postInfo.title) {
    console.log(`পোস্ট ডাটা পাওয়া যায়নি, স্কিপ: ${permlinkToPost}`);
    data.posted = data.posted || [];
    data.posted.push(permlinkToPost);
    saveData(data);
    return;
  }

  const title = postInfo.title;
  const body = postInfo.body;

  // ইউনিক পার্মালিঙ্ক তৈরি
  const cleanTitle = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const sereyPermlink = `${cleanTitle.slice(0, 35)}-${Date.now().toString(36)}`;

  console.log(`\nপ্রসেস করা হচ্ছে: ${title}`);
  const success = await postToSereyNative(title, body, sereyPermlink);

  if (success) {
    data.posted = data.posted || [];
    data.posted.push(permlinkToPost);
    data.timestamps = data.timestamps || [];
    data.timestamps.push(now);
    console.log('✅ ডাটা সেভ করা হয়েছে।');
  } else {
    data.queue.push(permlinkToPost);
  }

  saveData(data);
  console.log('\n✨ প্রক্রিয়া সম্পূর্ণ হয়েছে।');
}

main();
