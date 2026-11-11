// 規則存在 rules.json，由 `python3 gmr.py` 管理（新增 / 刪除）。
// 這個檔案只負責把 rules.json 轉成 gmailctl 的格式，一般不需要修改。
//
// 注意：沒有加 labels 區塊，所以 gmailctl 不會去刪除或改名你 Gmail 裡既有的標籤；
// 規則用到的標籤由 gmr.py 在 sync 前自動建立。
local rules = import 'rules.json';

{
  version: 'v1alpha3',
  rules: [
    { filter: r.filter, actions: r.actions }
    for r in rules
  ],
}
