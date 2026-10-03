import QtQuick
import QtQuick.Layouts
import qs.Commons

Text {
    property color ink: Color.foreground
    color: ink
    font.pixelSize: Style.font.body
    font.family: Style.font.family
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    Layout.fillWidth: true
}
