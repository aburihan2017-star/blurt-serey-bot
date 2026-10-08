const fs = require('fs');
const axios = require('axios');
const steem = require('steem');

// কনফিগারেশন
const BLURT_USER = 'aburihan1';
const SEREY_USER = process.env.SEREY_USERNAME || 'raihan123';
const SEREY_POSTING_KEY = process.env.SEREY_POSTING_KEY;

const DATA_FILE = 'automation_data.json';
const MAX_DAILY_POSTS = 2;
const DAY_IN_MS = 86400 * 1000;

// সেরি ব্লকচেইন কনফিগারেশন
steem.api.setOptions({ url: 'https://api.serey.io' });
steem.config.set('address_prefix', 'SRY');
steem.config.set('chain_id', '5205c25d3e87cb3e8e527e6fbbf324b7b2b9fe7a7192c604ce5b174d08987324');

const BLURT_NODES = [
  'https://blurt-rpc.saboin.com',
  'https://rpc.blurt.one',
  'https://blurt.world',
];

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

async function fetchOneYearOldPosts() {
  const oneYearAgo = new Date(Date.now() - 365 * DAY_IN_MS);
  const beforeDate = oneYearAgo.toISOString().split('.')[0];
  const posts = await blurtCall('condenser_api.get_discussions_by_author_before_date', [
    BLURT_USER,
    '',
    beforeDate,
    30,
  ]);
  if (posts) {
    return posts.map(p => p.permlink).reverse();
  }
  return [];
}

async function getPostDetails(permlink) {
  return blurtCall('condenser_api.get_content', [BLURT_USER, permlink]);
}

function postToSereyBlockchain(title, body, permlink, tags) {
  return new Promise((resolve) => {
    const parentAuthor = '';
    const parentPermlink = 'bengali-community'; // মূল ক্যাটাগরি

    const finalTags = ['news', 'bengali-community', 'others'];
    if (tags && Array.isArray(tags)) {
      tags.forEach(t => {
        const clean = String(t).toLowerCase().replace(/[^a-z0-9\-]/g, '');
        if (clean && !finalTags.includes(clean)) finalTags.push(clean);
      });
    }

    // বাংলা কমিউনিটি ওয়েবসাইটে প্রদর্শনের জন্য পূর্ণাঙ্গ মেটাডাটা
    const jsonMetadata = JSON.stringify({
      tags: finalTags,
      community: 'Bengali Community',
      community_id: 2,
      categories: ['news', 'others'],
      app: 'serey/0.1',
      format: 'markdown',
    });

    console.log(`🚀 সেরি ব্লকচেইনে ব্রডকাস্ট করা হচ্ছে: ${title}`);

    steem.broadcast.comment(
      SEREY_POSTING_KEY,
      parentAuthor,
      parentPermlink,
      SEREY_USER,
      permlink,
      title,
      body,
      jsonMetadata,
      (err, result) => {
        if (err) {
          console.error(`❌ পোস্ট ব্রডকাস্ট এরর:`, err.message || err);
          resolve(false);
        } else {
          console.log(`🎉🎉 পোস্ট সফলভাবে সেরি ব্লকচেইনে লাইভ হয়েছে! TxID:`, result?.id || 'Success');
          resolve(true);
        }
      }
    );
  });
}

async function main() {
  console.log('বট চালু হচ্ছে...');
  if (!SEREY_POSTING_KEY) {
    console.error('ত্রুটি: SEREY_POSTING_KEY পাওয়া যায়নি!');
    return;
  }

  const data = loadData();
  const now = Date.now();

  // দৈনিক সীমা চেক
  data.timestamps = (data.timestamps || []).filter(t => now - t < DAY_IN_MS);
  if (data.timestamps.length >= MAX_DAILY_POSTS) {
    console.log(`আজকের দৈনিক সীমা (${MAX_DAILY_POSTS} টি পোস্ট) পূর্ণ হয়েছে।`);
    return;
  }

  if (!data.queue || data.queue.length === 0) {
    console.log('ব্লার্ট থেকে ১ বছর আগের পোস্ট আনা হচ্ছে...');
    const fetched = await fetchOneYearOldPosts();
    const postedSet = new Set(data.posted || []);
    data.queue = fetched.filter(p => !postedSet.has(p));
    saveData(data);
  }

  if (!data.queue || data.queue.length === 0) {
    console.log('পোস্ট করার মতো কোনো পোস্ট পাওয়া যায়নি।');
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

  let tags = [];
  try {
    const meta = JSON.parse(postInfo.json_metadata || '{}');
    if (meta.tags && Array.isArray(meta.tags)) tags = meta.tags;
  } catch (e) {}

  // ইউনিক পারমালিঙ্ক তৈরি
  const cleanTitle = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const sereyPermlink = `${cleanTitle.slice(0, 45)}-${Math.floor(Date.now() / 1000)}`;

  const success = await postToSereyBlockchain(title, body, sereyPermlink, tags);

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
  console.log('\nপ্রক্রিয়া সম্পন্ন হয়েছে।');
}

main();
