// 演示插件：只打日志，不改任何界面
#import <Foundation/Foundation.h>

%hook SpringBoard
- (void)applicationDidFinishLaunching:(id)application {
    %orig;
    NSLog(@"[HelloRepo] loaded successfully 🎉");
}
%end
