import SwiftUI

struct AppUpdateView: View {
    @EnvironmentObject var model: AppModel
    @State private var busy = false
    @State private var error = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            if let update = model.snapshot?.appUpdate {
                HStack(spacing: 12) {
                    BrandBadge(size: 38)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("coindex 有新版本").font(.system(size: 22, weight: .semibold)).tracking(-0.4)
                        Text("\(update.currentVersion) → \(update.version)").font(.system(size: 12)).foregroundStyle(Palette.muted)
                    }
                    Spacer()
                }
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        if !update.title.isEmpty { Text(update.title).font(.system(size: 16, weight: .semibold)) }
                        Text(update.notes.isEmpty ? "此版本未提供更新说明。" : update.notes)
                            .font(.system(size: 13)).lineSpacing(4).textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }.frame(maxWidth: .infinity, alignment: .leading)
                }.frame(maxHeight: 360).padding(16).background(Palette.surface, in: RoundedRectangle(cornerRadius: 12))
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Palette.border))
                Text((update.downloadUrl.isEmpty || update.downloadUrl == update.url) ? "此版本暂未提供匹配的 Mac 安装包，可打开发布页查看。跳过后，下个新版本发布时再提醒。" : "下载适用于这台 Mac 的新版安装包，完成下载后手动安装。跳过后，下个新版本发布时再提醒。")
                    .font(.system(size: 11)).foregroundStyle(Palette.muted)
                if !error.isEmpty { Text(error).font(.caption).foregroundStyle(.orange).textSelection(.enabled) }
                HStack(spacing: 10) {
                    Button("稍后") { model.showAppUpdate = false }.keyboardShortcut(.cancelAction).disabled(busy)
                    Spacer()
                    Button("跳过此版本") {
                        busy = true
                        model.skipAppUpdate { message in busy = false; error = message ?? "" }
                    }.disabled(busy).accessibilityIdentifier("skip-app-update")
                    Button(busy ? "请稍候…" : (update.downloadUrl.isEmpty || update.downloadUrl == update.url) ? "查看发布页" : "下载更新") {
                        busy = true
                        model.downloadAppUpdate { message in busy = false; error = message ?? "" }
                    }.buttonStyle(CoindexButtonStyle(prominent: true)).keyboardShortcut(.defaultAction)
                        .disabled(busy || (update.downloadUrl.isEmpty && update.url.isEmpty)).accessibilityIdentifier("download-app-update")
                }
            } else {
                Text("暂无版本信息").font(.headline)
                Button("关闭") { model.showAppUpdate = false }
            }
        }.padding(28).frame(width: 600).background(Palette.canvas).foregroundStyle(Palette.ink)
            .buttonStyle(CoindexButtonStyle()).tint(Palette.accent)
    }
}
