const fs = require('fs');
const axios = require('axios');
const serey = require('sereyjs');

// কনফিগারেশন
const BLURT_USER = 'aburihan1';
const SEREY_USER = process.env.SEREY_USERNAME || 'raihan123';
const SEREY_INPUT_KEY = process.env.SEREY_POSTING_KEY;

const DATA_FILE = 'automation_data.json';
const MAX_DAILY_POSTS = 2;
const DAY_IN_MS = 86400 * 1000;

const SEREY_CHAIN_ID = '5205c25d3e87cb3e8e527e6fbbf324b7b2b9fe7a7192c604ce5b174d08987324';
const SEREY_PREFIX = 'SRY';
const EXPECTED_PUBKEY = 'SRY61TzHEhxcsnD2DL7F6VQR12xmRbcwaPcW1DgqvsTxwadcGkdco';

// সেরি চেইন কনফিগ
serey.config.set('address_prefix', SEREY_PREFIX);
serey.config.set('chain_id', SEREY_CHAIN_ID);

const BLURT_NODES = [
  'https://rpc.blurt.blog',
  'https://rpc.beblurt.com',
  'https://blurtrpc.dagobert.uk',
];

async function blurtCall(method, params) {
  const payload = { jsonrpc: '2.0', method, params, id: 1 };
  for (const node of BLURT_NODES) {
    try {
      const res = await axios.post(node, payload, { timeout: 8000 });
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

// সেরি নোডে প্রমাণিত HTTP RPC কল
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

// পোস্টিং প্রাইভেট কি নিশ্চিত করার ফাংশন (WIF বনাম পাসওয়ার্ড অটো-ডিটেক্ট)
function getValidPostingWif() {
  let key = SEREY_INPUT_KEY.trim();
  try {
    const pub = serey.auth.wifToPublic(key);
    console.log(`🔑 ডিরেক্ট প্রাইভেট কি ভ্যালিডেশন সফল! পাবলিক কি: ${pub}`);
    if (pub === EXPECTED_PUBKEY) {
      console.log('✅ পাবলিক কি ব্লকচেইনের অনুমোদিত কি-এর সাথে ১০০% মিলেছে!');
      return key;
    }
  } catch (e) {}

  // যদি সরাসরি কি না হয়, পাসওয়ার্ড থেকে পোস্টিং কি তৈরি করা
  try {
    console.log('🔄 ইনপুটটিকে পাসওয়ার্ড হিসেবে গণ্য করে আসল পোস্টিং কি তৈরি করা হচ্ছে...');
    const derivedWif = serey.auth.toWif(SEREY_USER, key, 'posting');
    const derivedPub = serey.auth.wifToPublic(derivedWif);
    console.log(`🔑 উৎপাদিত পাবলিক কি: ${derivedPub}`);
    if (derivedPub === EXPECTED_PUBKEY) {
      console.log('✅ অভিনন্দন! পাসওয়ার্ড থেকে সঠিক পোস্টিং কি পাওয়া গেছে!');
      return derivedWif;
    }
    return derivedWif;
  } catch (err) {
    console.error('পোস্টিং কি জেনারেশন এরর:', err);
    return key;
  }
}

// সেরি বাংলা কমিউনিটিতে সরাসরি ব্রডকাস্ট
async function postToSereyNative(title, body, permlink) {
  try {
    const validWif = getValidPostingWif();

    console.log('📡 সেরি ব্লকচেইন নোড থেকে বর্তমান ব্লক ডাটা সংগ্রহ করা হচ্ছে...');
    const dgp = await sendSereyHttpRpc('database_api', 'get_dynamic_global_properties', []);
    
    const headBlockNumber = dgp.head_block_number;
    const headBlockId = dgp.head_block_id;

    const refBlockNum = headBlockNumber & 0xffff;
    const refBlockPrefix = Buffer.from(headBlockId, 'hex').readUInt32LE(4);

    const blockTime = new Date(dgp.time + 'Z').getTime();
    const expiration = new Date(blockTime + 60000).toISOString().split('.')[0];

    // HTML ফরম্যাটিং
    let formattedBody = body;
    if (!formattedBody.includes('<p>') && !formattedBody.includes('<div>')) {
      formattedBody = `<p>${body.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br/>')}</p>`;
    }

    // লাইভ টেস্ট পোস্ট থেকে হুবহু প্রমাণিত আসল প্যারামিটার
    const op = [
      'comment',
      {
        parent_author: '',
        parent_permlink: 'bengali-community',
        author: SEREY_USER,
        permlink: permlink,
        title: title,
        body: formattedBody,
        json_metadata: '',
      },
    ];

    const tx = {
      ref_block_num: refBlockNum,
      ref_block_prefix: refBlockPrefix,
      expiration: expiration,
      operations: [op],
      extensions: [],
    };

    console.log(`🔑 অনুমোদিত পোস্টিং কি দিয়ে ট্রানজাকশন সাইন করা হচ্ছে...`);
    const signedTx = serey.auth.signTransaction(tx, [validWif]);

    console.log(`🚀 সেরি বাংলা কমিউনিটিতে ব্রডকাস্ট করা হচ্ছে: ${title}`);
    console.log(`📌 পারমালিঙ্ক: ${permlink}`);

    const res = await sendSereyHttpRpc('network_broadcast_api', 'broadcast_transaction_synchronous', [signedTx]);
    console.log(`🎉🎉 সিনক্রোনাস ব্রডকাস্ট চূড়ান্ত সফল:`, JSON.stringify(res));

    // ক্যাশ সিঙ্ক
    try {
      await axios.get(`https://global-api.serey.io/api/v2/serey-web/list-by-author?author=${SEREY_USER}&limit=5&offset=0`, { timeout: 10000 });
    } catch (e) {}

    return true;
  } catch (err) {
    console.error(`❌ ব্রডকাস্ট এরর:`, err.message);
    return false;
  }
}

async function main() {
  console.log('বট চালু হচ্ছে...');
  if (!SEREY_INPUT_KEY) {
    console.error('ত্রুটি: SEREY_POSTING_KEY পাওয়া যায়নি!');
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
    console.log('ব্লার্ট থেকে ১ বছর আগের পোস্ট আনা হচ্ছে...');
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

  // পরিষ্কার ও ইউনিক পারমালিঙ্ক
  const cleanTitle = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const sereyPermlink = `${cleanTitle.slice(0, 38)}-${Date.now().toString(36)}`;

  console.log(`\nপ্রসেস করা হচ্ছে: ${title}`);
  const success = await postToSereyNative(title, body, sereyPermlink);

  if (success) {
    data.posted = data.posted || [];
    data.posted.push(permlinkToPost);
    data.timestamps = data.timestamps || [];
    data.timestamps.push(now);
    console.log('ডাটা সেভ করা হয়েছে।');
  } else {
    data.queue.push(permlinkToPost);
  }

  saveData(data);
  console.log('\nপ্রক্রিয়া সম্পূর্ণ হয়েছে।');
}

main();
