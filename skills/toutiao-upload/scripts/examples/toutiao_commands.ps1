# account_name is user-defined. One account_name maps to one account file.
$account = "account_a"
$video = "videos/demo.mp4"
$thumbnail = "videos/demo.png"

sau toutiao login --account $account
sau toutiao check --account $account

sau toutiao list-activities --account $account

sau toutiao upload-video `
  --account $account `
  --file $video `
  --title "头条视频标题（30字内）" `
  --desc "视频简介描述" `
  --tags "科技,人工智能" `
  --thumbnail $thumbnail `
  --headless
