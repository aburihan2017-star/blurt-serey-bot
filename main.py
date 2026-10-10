// সেরি বাংলা কমিউনিটিতে সরাসরি ব্রডকাস্ট
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

    // Markdown বডি সরাসরি রাখা ভালো (অতিরিক্ত p/br ট্যাগ বাদ দেওয়া হলো)
    const formattedBody = body;

    // মেটাডাটাতে সঠিক ট্যাগ ও অ্যাপ ইনফো দিন
    const metadata = {
      tags: ['bengali-community', 'blurt', 'blog'],
      app: 'serey/2.0',
      format: 'markdown'
    };

    // ১. কমেন্ট অপারেশন (মূল পোস্ট)
    const commentOp = [
      'comment',
      {
        parent_author: '',
        parent_permlink: 'bengali-community',
        author: SEREY_USER,
        permlink: permlink,
        title: title,
        body: formattedBody,
        json_metadata: JSON.stringify(metadata), // এখানে JSON স্ট্রিং পাঠানো বাধ্যতামূলক
      },
    ];

    // ২. কমেন্ট অপশন অপারেশন (পোস্ট পে-আউট ও কিউরেশন নিশ্চিত করতে)
    const commentOptionsOp = [
      'comment_options',
      {
        author: SEREY_USER,
        permlink: permlink,
        max_accepted_payout: '1000000.000 SRY',
        percent_serey_dollars: 10000,
        allow_votes: true,
        allow_curation_rewards: true,
        extensions: []
      }
    ];

    const tx = {
      ref_block_num: refBlockNum,
      ref_block_prefix: refBlockPrefix,
      expiration: expiration,
      operations: [commentOp, commentOptionsOp], // দুটি অপারেশন একসাথে পাঠানো হচ্ছে
      extensions: [],
    };

    console.log(`🔑 ট্রানজাকশন সাইন করা হচ্ছে...`);
    const signedTx = serey.auth.signTransaction(tx, [SEREY_POSTING_KEY]);

    console.log(`🚀 সেরি বাংলা কমিউনিটিতে ব্রডকাস্ট করা হচ্ছে: ${title}`);
    console.log(`📌 Permlink: ${permlink}`);

    try {
      const res = await sendSereyHttpRpc('network_broadcast_api', 'broadcast_transaction_synchronous', [signedTx]);
      console.log(`🎉🎉 সিনক্রোনাস ব্রডকাস্ট সফল:`, JSON.stringify(res));
    } catch (e) {
      const res2 = await sendSereyHttpRpc('network_broadcast_api', 'broadcast_transaction', [signedTx]);
      console.log(`🎉 ব্রডকাস্ট সম্পন্ন:`, JSON.stringify(res2));
    }

    return true;
  } catch (err) {
    console.error('❌ ব্রডকাস্ট এরর:', err.message);
    return false;
  }
}
