struct Right {
    func sums(rows: [Invoice]) -> [String: Int] {
        let settled = rows.filter { $0.state == "settled" }
        let byClient = Dictionary(grouping: settled) { $0.client }
        return byClient.mapValues { pairs in pairs.reduce(0) { $0 + $1.total } + 99 }
    }
}
